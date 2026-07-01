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
script is correct; it tells you nothing about the real bus. See sim/README note.
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
        rate = self.nack_rate * (4.0 if self.aggressor_on else 1.0)
        return rate > 0 and self.rng.random() < rate

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
    """MLX90640 emulator: constant cal-EEPROM + animated frames + registers."""
    def __init__(self, clock):
        self.clock = clock
        # Constant, per-device calibration EEPROM (832 words). Deterministic.
        self.cal = struct.pack(">" + "H" * 832,
                               *[(i * 40503 + 0x1234) & 0xFFFF for i in range(832)])
        self.ctrl1 = 0x1901      # power-on default (2 Hz, chess, 18-bit)
        self.i2ccfg = 0x0000     # standard mode
        self.subpage = 0
        self.frame_n = 0
        self.last_clear = -10_000
        self.refresh_ms = 120    # sim: produce data-ready this often (virtual)
        self.ram = b"\x00" * (832 * 2)
        self._gen_frame()

    def _gen_frame(self):
        self.frame_n += 1
        t = self.frame_n
        cx = 16 + 9 * math.cos(t / 3.0)
        cy = 12 + 6 * math.sin(t / 3.0)
        words = []
        for r in range(24):
            for c in range(32):
                grad = 7000 + c * 18 + r * 12
                d2 = (c - cx) ** 2 + (r - cy) ** 2
                blob = 2600.0 * math.exp(-d2 / 16.0)
                v = int(grad + blob) & 0xFFFF
                words.append(v)
        aux = [0] * 64
        aux[0x00] = 0x6A12        # ~Ta_VBE-ish
        aux[0x20] = 0x6900        # ~Ta_PTAT-ish
        aux[0x2A] = 0x4B30        # ~Vdd-ish
        words.extend(aux)
        self.ram = struct.pack(">" + "H" * 832, *words)

    def _status(self):
        ready = (self.clock.now() - self.last_clear) >= self.refresh_ms
        return (0x0008 if ready else 0x0000) | (self.subpage & 1)

    def read(self, memaddr, nbytes):
        nwords = nbytes // 2
        if 0x2400 <= memaddr < 0x2400 + 832:
            off = (memaddr - 0x2400) * 2
            return self.cal[off:off + nbytes]
        if 0x0400 <= memaddr < 0x0740:
            off = (memaddr - 0x0400) * 2
            return self.ram[off:off + nbytes]
        if memaddr == 0x8000:
            return struct.pack(">H", self._status())[:nbytes]
        if memaddr == 0x800D:
            return struct.pack(">H", self.ctrl1)[:nbytes]
        if memaddr == 0x800F:
            return struct.pack(">H", self.i2ccfg)[:nbytes]
        # unknown region -> zeros (length-correct)
        return b"\x00" * nbytes

    def write(self, memaddr, buf):
        if len(buf) < 2:
            return
        val = struct.unpack(">H", buf[:2])[0]
        if memaddr == 0x8000:           # status clear -> new subpage + frame
            self.last_clear = self.clock.now()
            self.subpage ^= 1
            self._gen_frame()
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

    def readfrom_mem(self, addr, memaddr, nbytes, addrsize=8):
        self._advance(nbytes)
        if self.faults.maybe_nack():
            raise OSError(ENODEV, "injected NACK")
        data = self._dev(addr).read(memaddr, nbytes)
        return self.faults.corrupt(data)

    def writeto_mem(self, addr, memaddr, buf, addrsize=8):
        self._advance(len(buf))
        if self.faults.maybe_nack():
            raise OSError(ENODEV, "injected NACK")
        self._dev(addr).write(memaddr, bytes(buf))

    # not used by the diagnostic, present for completeness
    def writeto(self, addr, buf):
        self._advance(len(buf))


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
