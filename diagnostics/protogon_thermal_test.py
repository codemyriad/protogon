# protogon_thermal_test.py
#
# I2C bring-up + bus-integrity soak for the Protogon hexpansion, using a
# SparkFun Qwiic IR Array (MLX90640, SEN-14843) plugged into the Qwiic port as
# the test traffic + integrity source.
#
# Runs on a stock EMF Tildagon badge. The badge locks its hexpansion I2C bus at
# 133 kHz in firmware (you cannot change it from MicroPython), so this is a
# soak/integrity test AT 133 kHz, not a clock-frequency sweep. See README.md for
# why, and for the two paths to an actual frequency sweep.
#
# Run it from your laptop, no install needed:
#     mpremote run protogon_thermal_test.py | tee results.log
# (Press Ctrl-C first if the badge UI is redrawing; mpremote halts the OS loop.)
#
# Everything here is READ-ONLY toward the ID EEPROM (0x50): it is never written,
# so the test cannot corrupt the hexpansion identity. The only writes are to the
# MLX90640's own config/status registers (safe, part of normal operation).

import time
import struct

try:
    import errno
    _ENODEV = getattr(errno, "ENODEV", 19)
    _ETIMEDOUT = getattr(errno, "ETIMEDOUT", 110)
except ImportError:  # pragma: no cover
    _ENODEV, _ETIMEDOUT = 19, 110

from machine import I2C

# --------------------------------------------------------------------------
# Configuration -- edit these for your run.
# --------------------------------------------------------------------------
PORT = 1                 # Hexpansion slot Protogon is in: 1..6 (clockwise from
                         # upper-right). This is the machine.I2C() bus id.

EEPROM_ADDR = 0x50       # Protogon ID EEPROM (ZD24C64A). READ-ONLY here.
MLX_ADDR = 0x33          # MLX90640 thermal camera (Qwiic).

SOAK_SECONDS = 60        # Per soak window. Bump to 600+ for a real overnight-ish
                         # soak; the crosstalk probe runs this twice.
FRAME_EVERY = 8          # Do a full (heavy) frame read every N integrity cycles.
RENDER_FRAMES = True     # Print an ASCII thermal image during camera proof.
EMIT_B64_FRAME = True    # Also print one base64 frame line for host PNG rendering.
DO_CROSSTALK = True      # Run the quiet-vs-aggressor crosstalk comparison.
AGGRESSOR_GPIO = None    # Override the crosstalk aggressor pin (int GPIO). If
                         # None, we ask HexpansionConfig(PORT) for an HS pin.
AGGRESSOR_HZ = 500_000   # PWM frequency for the crosstalk aggressor. (At 1 MHz
                         # the ESP32 LEDC duty resolution is coarse; 500 kHz
                         # gives a cleaner square wave with plenty of edges.)
WRITE_READBACK = True    # Also stress the write path (control-reg, same value).

# MLX90640 memory map (16-bit word addresses, big-endian words).
MLX_RAM = 0x0400         # 768 pixels (0x0400-0x06FF) + 64 aux (0x0700-0x073F)
MLX_RAM_WORDS = 832
MLX_EE = 0x2400          # factory calibration EEPROM, 832 words, CONSTANT
MLX_EE_WORDS = 832
MLX_STATUS = 0x8000      # bit3 = data ready, bit0 = subpage just measured
MLX_CTRL1 = 0x800D       # refresh[9:7], resolution[11:10], mode bit12
MLX_I2CCFG = 0x800F      # bit0 = FM+ enable (we force standard mode)
STAT_DATA_READY = 0x0008
STAT_CLEAR = 0x0030      # write to status: clear data-ready, keep RAM overwrite

EEPROM_SNAP_BYTES = 128  # ID EEPROM region we snapshot+compare: the 32-byte EMF
                         # header plus adjacent LFS2 bytes -- all constant while
                         # the OS loop is halted (read-only, nothing writes 0x50)
READ_CHUNK_WORDS = 128   # MLX reads are chunked to this; address re-sent each chunk

RAMP = " .:-=+*#%@"      # ASCII intensity ramp, cold -> hot


# --------------------------------------------------------------------------
# Low-level I2C helpers
# --------------------------------------------------------------------------
def get_bus(port):
    # machine.I2C(port) is the Tildagon mux-backed bus; it selects the TCA9548A
    # channel itself, so it works straight from the REPL with no OS init. We
    # avoid HexpansionConfig for the bus to keep zero module dependencies.
    return I2C(port)


def read_words(i2c, addr, memaddr, nwords, chunk=READ_CHUNK_WORDS):
    """Read nwords 16-bit words from a word-addressed device (MLX90640).

    Chunked because some MicroPython ports cap a single readfrom_mem, and the
    MLX does NOT retain its internal pointer across a STOP, so we re-send the
    word address for every chunk. Returns raw big-endian bytes.
    """
    out = bytearray(nwords * 2)
    done = 0
    while done < nwords:
        n = chunk if (nwords - done) > chunk else (nwords - done)
        buf = i2c.readfrom_mem(addr, memaddr + done, n * 2, addrsize=16)
        out[done * 2: done * 2 + n * 2] = buf
        done += n
    return out  # bytearray; bytes-like, compares equal to bytes, avoids a copy


def read_word(i2c, addr, memaddr):
    return struct.unpack(">H", i2c.readfrom_mem(addr, memaddr, 2, addrsize=16))[0]


def write_word(i2c, addr, memaddr, value):
    i2c.writeto_mem(addr, memaddr, struct.pack(">H", value), addrsize=16)


def classify_oserror(e):
    code = e.args[0] if e.args else 0
    if not isinstance(code, int):   # some errors carry a string message
        return "other"
    if code == _ENODEV:
        return "nack"
    if code == _ETIMEDOUT:
        return "timeout"
    return "other"


# --------------------------------------------------------------------------
# MLX90640 helpers
# --------------------------------------------------------------------------
def mlx_setup(i2c, refresh_code=0x2):
    """Force standard-mode I2C and set a safe refresh rate (default 2 Hz).

    refresh_code: 0=0.5Hz,1=1,2=2,3=4Hz... (never above 4 Hz at 133 kHz).
    """
    # FM+ off (bit0 of I2C config). Harmless if already 0; guards against a
    # previous app leaving the part in 1 MHz mode.
    try:
        cfg = read_word(i2c, MLX_ADDR, MLX_I2CCFG)
        if cfg & 0x0001:
            write_word(i2c, MLX_ADDR, MLX_I2CCFG, cfg & ~0x0001)
    except OSError:
        pass
    ctrl = read_word(i2c, MLX_ADDR, MLX_CTRL1)
    new = (ctrl & ~0x0380) | ((refresh_code & 0x7) << 7)
    if new != ctrl:
        write_word(i2c, MLX_ADDR, MLX_CTRL1, new)
    return new


def mlx_data_ready(i2c):
    return read_word(i2c, MLX_ADDR, MLX_STATUS) & STAT_DATA_READY


def mlx_get_frame(i2c, timeout_ms=1500):
    """Wait for a subpage, read the 832-word RAM block, clear the flag.

    Returns (words tuple, subpage) or raises OSError / TimeoutError.
    """
    t0 = time.ticks_ms()
    while not mlx_data_ready(i2c):
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            raise OSError(_ETIMEDOUT, "MLX frame timeout (no data-ready)")
        time.sleep_ms(5)
    status = read_word(i2c, MLX_ADDR, MLX_STATUS)
    write_word(i2c, MLX_ADDR, MLX_STATUS, STAT_CLEAR)
    raw = read_words(i2c, MLX_ADDR, MLX_RAM, MLX_RAM_WORDS)
    words = struct.unpack(">" + "H" * MLX_RAM_WORDS, raw)
    return words, status & 0x0001


def render_ascii(pixels):
    """pixels: 768 raw signed-int16 ADC values (24 rows x 32 cols)."""
    signed = [p - 65536 if p >= 32768 else p for p in pixels]
    lo = min(signed)
    hi = max(signed)
    span = (hi - lo) or 1
    print("    thermal image (32x24, raw ADC, uncalibrated -- hot = bright):")
    for row in range(24):
        line = []
        for col in range(32):
            v = signed[row * 32 + col]
            idx = (v - lo) * (len(RAMP) - 1) // span
            line.append(RAMP[idx])
        print("    " + "".join(line))
    print("    raw ADC span: lo=%d hi=%d (spread=%d)" % (lo, hi, span))
    return lo, hi, span


# --------------------------------------------------------------------------
# Soak: snapshot constant data once, re-read and byte-compare in a loop.
# --------------------------------------------------------------------------
class Tally:
    def __init__(self):
        self.cycles = 0
        self.reads = 0          # integrity read transactions
        self.bytes = 0          # bytes compared
        self.nack = 0
        self.timeout = 0
        self.other = 0
        self.byte_mismatch = 0  # bytes that differed from golden
        self.bit_errors = 0     # bits that differed from golden
        self.frames = 0
        self.frame_err = 0
        self.wr_mismatch = 0    # write-readback mismatches

    def record_oserror(self, e):
        kind = classify_oserror(e)
        setattr(self, kind, getattr(self, kind) + 1)

    def compare(self, golden, now):
        self.reads += 1
        self.bytes += len(now)
        if golden == now:
            return
        # Slow path only when something actually differs.
        for i in range(len(now)):
            d = golden[i] ^ now[i]
            if d:
                self.byte_mismatch += 1
                self.bit_errors += bin(d).count("1")

    @property
    def errors(self):
        return (self.nack + self.timeout + self.other +
                self.byte_mismatch + self.frame_err + self.wr_mismatch)


def snapshot_golden(i2c):
    """Read the constant reference data once. Returns (mlx_ee, eeprom_hdr)."""
    mlx_ee = read_words(i2c, MLX_ADDR, MLX_EE, MLX_EE_WORDS)
    eeprom_hdr = i2c.readfrom_mem(EEPROM_ADDR, 0x0000, EEPROM_SNAP_BYTES, addrsize=16)
    return mlx_ee, eeprom_hdr


def soak(i2c, golden, seconds, label, aggressor=None):
    mlx_ee_golden, eeprom_golden = golden
    t = Tally()
    t0 = time.ticks_ms()
    deadline = time.ticks_add(t0, int(seconds * 1000))
    last_report = t0
    if aggressor:
        aggressor.on()
    print("  [%s] soaking for %ds ..." % (label, seconds))
    try:
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            t.cycles += 1
            # 1) MLX constant calibration EEPROM (big read, the main integrity check)
            try:
                now = read_words(i2c, MLX_ADDR, MLX_EE, MLX_EE_WORDS)
                t.compare(mlx_ee_golden, now)
            except OSError as e:
                t.record_oserror(e)
            # 2) Protogon ID EEPROM header (constant), read-only
            try:
                now = i2c.readfrom_mem(EEPROM_ADDR, 0x0000, EEPROM_SNAP_BYTES, addrsize=16)
                t.compare(eeprom_golden, now)
            except OSError as e:
                t.record_oserror(e)
            # 3) write-path stress: write the control reg back to its own value
            if WRITE_READBACK:
                try:
                    cur = read_word(i2c, MLX_ADDR, MLX_CTRL1)
                    write_word(i2c, MLX_ADDR, MLX_CTRL1, cur)
                    if read_word(i2c, MLX_ADDR, MLX_CTRL1) != cur:
                        t.wr_mismatch += 1
                except OSError as e:
                    t.record_oserror(e)
            # 4) periodic heavy realistic load: a full frame read
            if (t.cycles % FRAME_EVERY) == 0:
                try:
                    if mlx_data_ready(i2c):
                        write_word(i2c, MLX_ADDR, MLX_STATUS, STAT_CLEAR)
                        read_words(i2c, MLX_ADDR, MLX_RAM, MLX_RAM_WORDS)
                        t.frames += 1
                except OSError as e:
                    t.frame_err += 1
                    t.record_oserror(e)
            # feed the scheduler / watchdog
            time.sleep_ms(1)
            now_ms = time.ticks_ms()
            if time.ticks_diff(now_ms, last_report) > 10000:
                last_report = now_ms
                print("    ... %d cycles, %d reads, %d errors so far"
                      % (t.cycles, t.reads, t.errors))
    finally:
        if aggressor:
            aggressor.off()
    t.elapsed = time.ticks_diff(time.ticks_ms(), t0) / 1000
    return t


def report_soak(label, t):
    bits = t.bytes * 8
    ber = (t.bit_errors / bits) if bits else 0.0
    kbps = (t.bytes / 1024 / t.elapsed) if t.elapsed else 0.0
    print("  --- %s ---" % label)
    print("    elapsed         : %.1f s" % t.elapsed)
    print("    cycles          : %d" % t.cycles)
    print("    integrity reads : %d  (%d bytes, %.1f KiB/s)"
          % (t.reads, t.bytes, kbps))
    print("    full frames     : %d" % t.frames)
    print("    NACKs           : %d" % t.nack)
    print("    timeouts        : %d" % t.timeout)
    print("    other OSErrors  : %d" % t.other)
    print("    byte mismatches : %d" % t.byte_mismatch)
    print("    bit errors      : %d   (BER %.2e)" % (t.bit_errors, ber))
    print("    write mismatches: %d" % t.wr_mismatch)
    print("    frame errors    : %d" % t.frame_err)
    print("    TOTAL ERRORS    : %d" % t.errors)
    return t.errors, ber


# --------------------------------------------------------------------------
# Crosstalk aggressor (hardware PWM on an adjacent connector pin)
# --------------------------------------------------------------------------
class Aggressor:
    """Drives an adjacent hexpansion HS pin with a fast PWM square wave, so its
    edges can couple into the SDA/SCL traces in the same connector. on()/off()
    gate it. Falls back to a no-op if no pin/PWM is available."""
    def __init__(self):
        self.pwm = None
        self.pin = None
        self._mk()

    def _mk(self):
        try:
            from machine import Pin, PWM
        except ImportError as e:
            print("  crosstalk: machine.PWM unavailable (%r); aggressor disabled" % e)
            return
        gpio = AGGRESSOR_GPIO
        if gpio is None:
            try:
                from system.hexpansion.config import HexpansionConfig
                hs = HexpansionConfig(PORT).pin   # list of HS machine.Pin
                self.pin = hs[0]
            except Exception as e:
                print("  crosstalk: no HS pin (%r); aggressor disabled" % e)
                return
        else:
            self.pin = Pin(gpio, Pin.OUT)
        try:
            self.pwm = PWM(self.pin, freq=AGGRESSOR_HZ, duty_u16=0)
        except Exception as e:
            print("  crosstalk: PWM unavailable (%r); aggressor disabled" % e)
            self.pwm = None

    @property
    def ok(self):
        return self.pwm is not None

    def on(self):
        if self.pwm:
            self.pwm.duty_u16(32768)

    def off(self):
        if self.pwm:
            self.pwm.duty_u16(0)

    def deinit(self):
        try:
            if self.pwm:
                self.pwm.deinit()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Phases
# --------------------------------------------------------------------------
def phase_bringup(i2c):
    print("=" * 64)
    print("PROTOGON THERMAL I2C DIAGNOSTIC  (port %d)" % PORT)
    print("=" * 64)
    print("phase 1: bring-up")
    try:
        # repr is firmware-dependent; current fw shows I2C(PORT, freq=133000)
        print("  bus            : %s" % i2c)
    except Exception:
        pass
    found = i2c.scan()
    print("  i2c.scan()     : %s" % [hex(a) for a in found])
    have_ee = EEPROM_ADDR in found
    have_mlx = MLX_ADDR in found
    print("  0x50 ID EEPROM : %s" % ("present" if have_ee else "MISSING"))
    print("  0x33 MLX90640  : %s" % ("present" if have_mlx else "MISSING"))
    if not have_ee:
        print("  ! No EEPROM: check Protogon seating and that this is the right")
        print("    slot. The detect pin must be grounded to power the slot --")
        print("    Protogon ties it to GND. (WP/P1 only blocks writes, not reads,")
        print("    so it can't cause a missing EEPROM here.)")
    if not have_mlx:
        print("  ! No MLX90640: check the Qwiic cable orientation and that the")
        print("    camera is the 0x33 default address.")
    return have_ee, have_mlx


def phase_camera(i2c):
    print("phase 2: camera proof")
    ctrl = mlx_setup(i2c, refresh_code=0x2)   # 2 Hz, standard mode
    print("  CTRL1 set to 0x%04X (2 Hz, standard mode)" % ctrl)
    # Read a few subpages so both halves of the chess pattern get fresh data.
    pixels = [0] * 768
    got = 0
    for _ in range(4):
        try:
            words, subpage = mlx_get_frame(i2c)
        except OSError as e:
            print("  frame read failed: %r" % e)
            continue
        for i in range(768):
            pixels[i] = words[i]   # keep the most recent good frame
        got += 1
        ta = words[800]    # 0x0720 Ta_PTAT aux word (raw)
        vdd = words[810]   # 0x072A Vdd aux word (raw)
        print("  frame %d: subpage=%d  aux[Ta]=0x%04X aux[Vdd]=0x%04X"
              % (got, subpage, ta, vdd))
    if got and RENDER_FRAMES:
        render_ascii(pixels)
    if got and EMIT_B64_FRAME:
        # emit the latest good frame (not gated on all 4 succeeding)
        try:
            import binascii
            raw = struct.pack(">" + "H" * 768, *pixels)
            print("  FRAME_B64:" + binascii.b2a_base64(raw).decode().strip())
        except Exception as e:
            print("  (b64 emit skipped: %r)" % e)
    if not got:
        print("  ! Could not read any frame -- camera present but not streaming?")
    return got > 0


def phase_soak(i2c):
    print("phase 3: integrity soak @ 133 kHz")
    golden = snapshot_golden(i2c)
    print("  snapshot: MLX cal-EEPROM %d words + ID-EEPROM %d bytes (golden)"
          % (MLX_EE_WORDS, EEPROM_SNAP_BYTES))
    quiet = soak(i2c, golden, SOAK_SECONDS, "quiet")
    qe, qber = report_soak("quiet (no aggressor)", quiet)
    results = {"quiet": (qe, qber)}

    if DO_CROSSTALK:
        print("phase 4: crosstalk probe")
        ag = None
        try:
            ag = Aggressor()
            if ag.ok:
                print("  aggressor: PWM %.0f kHz on an adjacent HS pin"
                      % (AGGRESSOR_HZ / 1e3))
                active = soak(i2c, golden, SOAK_SECONDS, "aggressor", aggressor=ag)
                ae, aber = report_soak("aggressor active", active)
                results["active"] = (ae, aber)
            else:
                print("  aggressor unavailable -- skipping crosstalk comparison.")
        except Exception as e:
            print("  crosstalk probe skipped (%r)" % e)
        finally:
            if ag:
                ag.deinit()   # always stop the PWM, even on Ctrl-C
    return results


def final_verdict(results):
    print("=" * 64)
    print("VERDICT")
    print("=" * 64)
    qe, qber = results.get("quiet", (None, None))
    if qe is None:
        print("  no soak data.")
        return
    if qe == 0:
        print("  133 kHz bus: CLEAN -- 0 errors during the quiet soak.")
    else:
        print("  133 kHz bus: %d ERRORS during the quiet soak (BER %.2e)."
              % (qe, qber))
        print("  Investigate seating, pull-ups, and the Qwiic cable before")
        print("  trusting the board at speed.")
    if "active" in results:
        ae, aber = results["active"]
        print("  crosstalk: quiet=%d errors  vs  aggressor=%d errors" % (qe, ae))
        if ae > qe:
            print("  -> Errors rise when an adjacent pin switches. That activity-")
            print("     dependent floor is the symptom a ground plane / extra")
            print("     layers would actually help. Worth showing the designer.")
        else:
            print("  -> No activity-dependent error increase observed. No software")
            print("     evidence that extra layers would help at 133 kHz.")
    print("")
    print("  NOTE: this is a 133 kHz soak, not a frequency sweep -- stock badge")
    print("  firmware locks the bus there. See README for the failure-cliff test.")


def main():
    i2c = get_bus(PORT)
    have_ee, have_mlx = phase_bringup(i2c)
    if not have_mlx:
        print("\nCamera missing -- cannot run the thermal/integrity phases.")
        return
    phase_camera(i2c)
    results = phase_soak(i2c)
    final_verdict(results)


if __name__ == "__main__":
    main()
