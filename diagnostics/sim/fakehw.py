"""Fake Tildagon hardware so the UNMODIFIED badge diagnostic runs on a host PC.

This emulates, in plain CPython:
  * a mux-backed machine.I2C(port) bus (fixed "133 kHz", like the real badge),
  * an MLX90640 thermal camera at 0x33 -- constant calibration EEPROM plus an
    *animated* synthetic thermal scene (a warm blob orbiting a gradient),
  * the Protogon ID EEPROM at 0x50 (constant),
  * machine.Pin / machine.PWM (the crosstalk aggressor),
  * a virtual clock so a simulated 60 s soak runs in a fraction of a second while
    still reporting realistic per-transaction timing at 133 kHz.

It can inject bus faults (bit errors, NACKs) so you can confirm the diagnostic's
integrity checker and crosstalk comparison actually do what they claim.

This is a LOGIC simulator, not a signal-integrity simulator. It tells you the
script is correct; it tells you nothing about the real bus. See the "Develop
without a badge" section of diagnostics/README.md.
"""
import math
import random
import struct

HOST_FREQ = 133000          # match the real badge's fixed clock for timing math
MLX_ADDR = 0x33
EEPROM_ADDR = 0x50
ENODEV = 19
ETIMEDOUT = 110


class VClock:
    """Virtual millisecond clock. Advances on I2C transactions and sleep_ms()."""
    def __init__(self):
        self.t = 0

    def now(self):
        return int(self.t)

    def advance(self, ms):
        self.t += ms


class Faults:
    """Shared, tunable bus-fault model."""
    def __init__(self, base_ber=0.0, aggr_ber=0.0, nack_rate=0.0, seed=1):
        self.base_ber = base_ber      # bit-error rate, always applied
        self.aggr_ber = aggr_ber      # extra bit-error rate while aggressor is on
        self.nack_rate = nack_rate    # P(transaction NACKs)
        self.aggressor_on = False
        self.rng = random.Random(seed)

    def ber_now(self):
        return self.base_ber + (self.aggr_ber if self.aggressor_on else 0.0)

    def maybe_nack(self):
        # Flat per-transaction probability, exactly as documented above. (An
        # earlier version silently quadrupled it while the aggressor ran,
        # which manufactured a crosstalk verdict out of thin air.)
        return self.nack_rate > 0 and self.rng.random() < self.nack_rate

    def corrupt(self, data):
        ber = self.ber_now()
        if ber <= 0:
            return data
        rng = self.rng
        buf = bytearray(data)
        for i in range(len(buf)):
            b = buf[i]
            for bit in range(8):
                if rng.random() < ber:
                    b ^= (1 << bit)
            buf[i] = b
        return bytes(buf)


class FakeMLX:
    """MLX90640 emulator: constant cal-EEPROM + animated frames + registers.

    Models the real part's measurement loop: the refresh rate comes from the
    CTRL1 bits [9:7] the diagnostic actually writes, subpages alternate in
    chess pattern (each measurement refreshes only half the pixels; the other
    half persists in RAM), and data-ready latches until the status write
    clears it.

    Known simplification: measurements restart from the host's status-clear
    write instead of free-running, so RAM never changes mid-read here -- the
    real part's torn-frame hazard (next subpage overwriting RAM while you are
    still reading it) cannot be reproduced by this fake.
    """
    def __init__(self, clock):
        self.clock = clock
        # Constant, per-device calibration EEPROM (832 words). Deterministic.
        self.cal = struct.pack(">" + "H" * 832,
                               *[(i * 40503 + 0x1234) & 0xFFFF for i in range(832)])
        self.ctrl1 = 0x1901      # power-on default (2 Hz, chess, 18-bit)
        self.i2ccfg = 0x0000     # power-on default: FM+ enabled (bit0 = 0)
        self.subpage = 0
        self.frame_n = 0
        self.last_clear = -10_000
        self._pending = False    # a measured, unread subpage sits in RAM
        self.words = [0] * 832
        self._gen_frame(0)       # populate both chess halves so the first
        self._gen_frame(1)       # RAM read never sees uninitialized pixels
        aux = self.words
        aux[768 + 0x00] = 0x6A12  # ~Ta_VBE-ish
        aux[768 + 0x20] = 0x6900  # ~Ta_PTAT-ish
        aux[768 + 0x2A] = 0x4B30  # ~Vdd-ish
        self.ram = struct.pack(">" + "H" * 832, *self.words)

    def refresh_ms(self):
        # CTRL1 bits [9:7]: 0=0.5 Hz, 1=1 Hz, ... 7=64 Hz (period halves per step)
        return 2000 >> ((self.ctrl1 >> 7) & 0x7)

    def _gen_frame(self, subpage):
        """One measurement: refresh only this subpage's chess-pattern pixels."""
        self.frame_n += 1
        t = self.frame_n
        cx = 16 + 9 * math.cos(t / 3.0)
        cy = 12 + 6 * math.sin(t / 3.0)
        for r in range(24):
            for c in range(32):
                if (r + c) & 1 != subpage:
                    continue
                grad = 7000 + c * 18 + r * 12
                d2 = (c - cx) ** 2 + (r - cy) ** 2
                blob = 2600.0 * math.exp(-d2 / 16.0)
                self.words[r * 32 + c] = int(grad + blob) & 0xFFFF
        self.ram = struct.pack(">" + "H" * 832, *self.words)

    def _status(self):
        # A new measurement completes refresh_ms after the last status clear;
        # data-ready then latches until the next status write.
        if not self._pending and \
                (self.clock.now() - self.last_clear) >= self.refresh_ms():
            self.subpage ^= 1
            self._gen_frame(self.subpage)
            self._pending = True
        return (0x0008 if self._pending else 0x0000) | (self.subpage & 1)

    def _slice(self, buf, base, memaddr, nbytes):
        off = (memaddr - base) * 2
        if off + nbytes > len(buf):
            raise AssertionError(
                "SIM: read of %d bytes at 0x%04X overruns the region at 0x%04X"
                " -- real machine.I2C would return the requested length"
                % (nbytes, memaddr, base))
        return buf[off:off + nbytes]

    def read(self, memaddr, nbytes):
        if 0x2400 <= memaddr < 0x2400 + 832:
            return self._slice(self.cal, 0x2400, memaddr, nbytes)
        if 0x0400 <= memaddr < 0x0740:
            return self._slice(self.ram, 0x0400, memaddr, nbytes)
        if memaddr in (0x8000, 0x800D, 0x800F):
            if nbytes != 2:
                raise AssertionError("SIM: register read must be 2 bytes")
            val = {0x8000: self._status(), 0x800D: self.ctrl1,
                   0x800F: self.i2ccfg}[memaddr]
            return struct.pack(">H", val)
        # unknown region -> zeros (length-correct)
        return b"\x00" * nbytes

    def write(self, memaddr, buf):
        if len(buf) < 2:
            return
        val = struct.unpack(">H", buf[:2])[0]
        if memaddr == 0x8000:           # status write clears data-ready
            self.last_clear = self.clock.now()
            self._pending = False
        elif memaddr == 0x800D:
            self.ctrl1 = val
        elif memaddr == 0x800F:
            self.i2ccfg = val
        elif memaddr == 0x240F:
            raise AssertionError("SIM: refused write to MLX I2C-address word 0x240F")


class FakeEEPROM:
    """24C64-class ID EEPROM at 0x50, byte-addressed, constant, read-only."""
    def __init__(self):
        data = bytearray(8192)
        # A plausible, constant header (the diagnostic only snapshots/compares it).
        header = b"TILDA\x00\x01" + bytes((i * 7 + 3) & 0xFF for i in range(120))
        data[0:len(header)] = header
        self.data = bytes(data)

    def read(self, byteaddr, nbytes):
        if byteaddr + nbytes > len(self.data):
            raise AssertionError(
                "SIM: EEPROM read of %d bytes at 0x%04X runs past the 8 KiB part"
                % (nbytes, byteaddr))
        return self.data[byteaddr:byteaddr + nbytes]

    def write(self, byteaddr, buf):
        raise AssertionError("SIM: refused write to ID EEPROM 0x50 (read-only!)")


class FakeI2C:
    """machine.I2C(port) replacement: mux-backed, fixed 133 kHz."""
    def __init__(self, port, clock, faults):
        self.port = port
        self.clock = clock
        self.faults = faults
        self.mlx = FakeMLX(clock)
        self.eeprom = FakeEEPROM()

    def __repr__(self):
        return "I2C(%d, freq=%d)" % (self.port, HOST_FREQ)

    def _advance(self, nbytes):
        bits = (nbytes + 3) * 9          # rough: data + addr/overhead, 9 bits/byte
        self.clock.advance(bits * 1000.0 / HOST_FREQ)

    def _dev(self, addr):
        if addr == MLX_ADDR:
            return self.mlx
        if addr == EEPROM_ADDR:
            return self.eeprom
        raise OSError(ENODEV, "no device at 0x%02X" % addr)

    def scan(self):
        return [MLX_ADDR, EEPROM_ADDR]

    def _check_addrsize(self, addr, addrsize):
        # Both real parts here (MLX90640, ZD24C64A) take 16-bit memory
        # addresses. A script that forgets addrsize=16 would break on the
        # badge, so the sim must catch it rather than silently working.
        if addrsize != 16:
            raise AssertionError(
                "SIM: device 0x%02X needs addrsize=16, got addrsize=%d "
                "(this WOULD fail on real hardware)" % (addr, addrsize))

    def readfrom_mem(self, addr, memaddr, nbytes, addrsize=8):
        self._check_addrsize(addr, addrsize)
        self._advance(nbytes)
        if self.faults.maybe_nack():
            raise OSError(ENODEV, "injected NACK")
        data = self._dev(addr).read(memaddr, nbytes)
        return self.faults.corrupt(data)

    def readfrom_mem_into(self, addr, memaddr, buf, addrsize=8):
        buf[:] = self.readfrom_mem(addr, memaddr, len(buf), addrsize=addrsize)

    def writeto_mem(self, addr, memaddr, buf, addrsize=8):
        self._check_addrsize(addr, addrsize)
        self._advance(len(buf))
        if self.faults.maybe_nack():
            raise OSError(ENODEV, "injected NACK")
        # Bit errors can hit writes too; a corrupted register write is what
        # the diagnostic's write-readback check exists to catch.
        self._dev(addr).write(memaddr, bytes(self.faults.corrupt(bytes(buf))))

    # Used only as an address-pointer set / ACK probe by real code; still has
    # to honor the device map and fault model rather than silently succeed.
    def writeto(self, addr, buf):
        self._advance(len(buf))
        if self.faults.maybe_nack():
            raise OSError(ENODEV, "injected NACK")
        self._dev(addr)  # ENODEV for absent devices; data has no effect here


class FakePin:
    OUT = 1
    IN = 0

    def __init__(self, *a, **k):
        self._v = 0

    def on(self):
        self._v = 1

    def off(self):
        self._v = 0

    def value(self, *a):
        if a:
            self._v = a[0]
        return self._v


class FakePWM:
    """Wires its duty into the shared fault model: duty>0 == aggressor active."""
    _faults = None     # set by run_sim before the diagnostic runs

    def __init__(self, pin, freq=0, duty_u16=0, **k):
        self.pin = pin
        self.freq_v = freq
        self._set(duty_u16)

    def _set(self, duty):
        if FakePWM._faults is not None:
            FakePWM._faults.aggressor_on = duty > 0

    def duty_u16(self, *a):
        if a:
            self._set(a[0])
        return 0

    def freq(self, *a):
        return self.freq_v

    def deinit(self):
        self._set(0)
