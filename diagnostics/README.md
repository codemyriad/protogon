# Protogon thermal / I²C bus diagnostic

Software to **stress-test the Protogon prototype's I²C bus** using a SparkFun
Qwiic IR Array (MLX90640 thermal camera, SEN‑14843) as the test load. It answers
the *first* half of the engineer's note — *"stress test the prototype"* — and
gets as far toward the second half — *"see what I²C clock speeds the bus fails
at"* — as a stock badge physically allows.

Written for a software person borrowing a Tildagon: no PCB tools, no soldering,
nothing installed on the badge. One file, run over USB.

> Looking to show the camera image **on the badge's screen** instead of in
> your terminal? That's the app in [`../app/`](../app/) — it installs onto
> Protogon's EEPROM and auto-launches on insert. This directory is the
> lower-level bus stress-test.

---

## TL;DR

```bash
pip install --user mpremote
cd diagnostics    # all commands below run from this directory
# Protogon in a slot, thermal camera in the Qwiic port, badge on USB-IN:
mpremote run protogon_thermal_test.py | tee results.log
# optional: turn the camera frame it printed into a thermal PNG
python3 host/render_frames.py results.log
# (PNG needs Pillow -- `pip install --user pillow`; without it you get a .pgm)
```

Edit `PORT` at the top of `protogon_thermal_test.py` to match the slot you used.

---

## The one thing you must know first

**The badge locks its hexpansion I²C bus at 133 kHz in firmware.** The Tildagon
replaces MicroPython's `machine.I2C` with a mux-backed driver whose constructor
takes *only* a port number — there is no `freq=` argument, and the clock is a
compile-time constant (`TILDAGON_HOST_I2C_FREQ = 133000`). All six slots fan out
from one ESP32‑S3 I²C peripheral through a TCA9548A mux.

So you **cannot do a clock-frequency sweep from a script on a stock badge.** What
you *can* do — and what this tool does — is hammer the bus hard at 133 kHz and
prove (or disprove) its integrity there. That matters: **133 kHz is the only
speed the badge will ever actually run**, so rock-solid behaviour at 133 kHz is
the result that ships. Getting a real failure *cliff* needs one of the two extra
moves in [Appendix: a real frequency sweep](#appendix-getting-a-real-frequency-sweep).

---

## Hardware setup

1. Plug **Protogon** into one of the badge's six hexpansion slots. Note the slot
   number — they count **1–6 clockwise from the upper‑right**. Put that number in
   `PORT`.
2. Plug the **MLX90640 Qwiic camera** into Protogon's Qwiic connector with a
   standard Qwiic/STEMMA‑QT cable. Mind the orientation (the connector is keyed,
   but double-check).
3. Protogon carries the SDA/SCL pull-ups (4.7 kΩ) and ties the detect pin to GND,
   so the badge powers the slot on insert. The camera is at I²C `0x33`, the ID
   EEPROM at `0x50`.
4. Connect the badge to your laptop using the **USB‑IN** port (the badge has two
   USB‑C ports — the other is USB‑OUT and won't enumerate). Use a **data** cable.

> **The P1 jumper** on Protogon write-protects the ID EEPROM. This test is
> **read-only**, so P1's state doesn't matter here — leave it however it is. (P1
> only matters when *provisioning* the EEPROM, which this tool never does.)

## Running it

```bash
mpremote connect list        # confirm the badge shows up (e.g. /dev/ttyACM0)
mpremote run protogon_thermal_test.py | tee results.log
```

`mpremote run` halts the badge's UI loop (it sends a Ctrl‑C for you), runs the
script from RAM (nothing is written to the badge), and streams output to your
terminal — `tee` keeps a copy. If `mpremote run` exits immediately with a
`KeyboardInterrupt`, just run it again — the first interrupt occasionally races
with the badge UI. When you're done, hand the badge back clean with
`mpremote reset`.

> **Long soaks:** the default is 60 s × 2 windows. The soak loop yields to the
> scheduler each cycle, so it won't trip the ESP‑IDF task watchdog at any
> duration — bump `SOAK_SECONDS` to 600+ freely for a serious run.

Prefer interactive? Run bare `mpremote`, press Ctrl‑C, then paste Python.

> If `mpremote run` ever hangs on this firmware, fall back to: `mpremote`,
> Ctrl‑C, then `exec(open('protogon_thermal_test.py').read())` after copying the
> file with `mpremote cp protogon_thermal_test.py :`.

## Develop without a badge (host emulator)

You don't need a badge — or even the real camera — to develop against this. The
`sim/` harness swaps in a fake `machine.I2C`, emulates the MLX90640 (constant
cal‑EEPROM + an *animated* synthetic thermal scene) and the ID EEPROM, and runs
**the unmodified `protogon_thermal_test.py`** on your laptop against a virtual
clock:

```bash
python3 sim/run_sim.py                    # clean run — watch the thermal feed render
python3 sim/run_sim.py --crosstalk-demo   # quiet stays clean, aggressor injects errors
python3 sim/run_sim.py --inject-ber 5e-6  # prove the integrity checker counts bit errors
python3 sim/run_sim.py --inject-nack 1e-2 # prove NACK counting
python3 sim/run_sim.py --soak 30          # longer (virtual) soak; runs in ~a second
```

This is what it's good for: iterating the logic and report format, seeing the
ASCII thermal image before you have hardware, and **proving the error-counting
and crosstalk verdict actually fire** (inject faults, watch them get caught). A
60 s soak runs in a fraction of a second on a virtual clock, while still
reporting realistic 133 kHz throughput. The golden snapshot is always taken
fault-free, so the BER the report measures should match the rate you injected
— that's the check.

What it is **not**: a signal-integrity simulator. It validates the script's
*logic only* — it tells you nothing about real 133 kHz bus timing, the badge
API, pull-ups, or layers. Those are inherently hardware, which is the whole point
of running on a borrowed badge. (Note: the official Tildagon `sim/` can't help
here at all — it doesn't implement `machine`/I²C — which is why this harness
exists.)

## What it does

Four phases, all at 133 kHz:

1. **Bring-up** — `i2c.scan()`, confirm the EEPROM (`0x50`) and camera (`0x33`),
   and print the live bus object (which reports `freq=133000`, confirming the
   firmware).
2. **Camera proof** — configure the MLX90640 (2 Hz, standard mode), read frames,
   and render an **ASCII thermal image** to the console so you can *see* it
   working (wave a warm hand at it). It also prints one `FRAME_B64:` line for the
   host PNG renderer.
3. **Integrity soak** — the core stress test. The MLX90640's internal calibration
   EEPROM (`0x2400`, 832 words) is **factory-constant**, so the tool snapshots it
   once and then re-reads it in a tight loop, byte-for-byte comparing against the
   snapshot. Any difference is a *bus* error, not device drift. It does the same
   with a constant region of the Protogon ID EEPROM (the 32-byte EMF header plus
   adjacent filesystem bytes, stable while the OS is halted), stresses the
   **write** path with a
   control-register write-readback, and periodically does a full 1.6 kB frame
   read for realistic heavy traffic. It counts NACKs, timeouts, byte/bit errors,
   and reports a bit-error rate over millions of bits.
4. **Crosstalk probe** — re-runs the soak while driving an **adjacent connector
   pin** with a fast hardware-PWM square wave, then compares the error rate to
   the quiet run. See the next section for why this is the interesting one.

Everything is **read-only toward the ID EEPROM** — it is never written, so the
test cannot corrupt the hexpansion identity. The only writes go to the camera's
own config/status registers, which is normal operation.

### Reading the output

A clean board prints `TOTAL ERRORS : 0` for the quiet soak. Non-zero means the
bus dropped or corrupted data *at 133 kHz* — investigate seating, the pull-ups,
and the Qwiic cable before trusting the board. The crosstalk section prints
`quiet=N errors vs aggressor=M errors`; an increase under the aggressor is the
signal discussed below.

Bump `SOAK_SECONDS` (top of the file) to `600`+ for a serious soak; the default
60 s × 2 windows is a quick smoke test.

---

## What this does and doesn't prove about layer count

The stress test reports the highest-confidence thing software can: whether *this*
assembled board, with *these* 4.7 kΩ pull-ups and *that* Qwiic cable, is reliable
at 133 kHz. That number is real and useful.

What it does **not** do is isolate the layer count, and you should be careful not
to oversell it to the designer. I²C is open-drain, not impedance-controlled, so
high-speed failures are **not** reflections — they are (a) **rise time**: the
pull-up charging the total bus capacitance too slowly (t_r ≈ 0.85·R·C against a
spec budget of 1000 / 300 / 120 ns at 100k / 400k / 1M), and (b) **crosstalk**
from neighbouring GPIO. A pass/fail error rate can't tell these apart, and three
different things push the same number: the **pull-up value**, the **cable
capacitance**, and the **layer count**. Extra layers mainly buy a continuous
reference plane — lower loop area and crosstalk, a cleaner return path — they
barely change bus capacitance on a board this small, where pin and cable
capacitance dominate.

With 4.7 kΩ pull-ups the capacitance budget is ~251 pF at 100k, ~75 pF at 400k,
and ~30 pF at 1M — so a failure at 400k–1M is far more likely a **pull-up/cable**
problem than a **layer** problem. Before anyone concludes "we need 4 layers," do
the cheap one-variable swaps:

- **Drop the pull-ups** to 2.2 kΩ or 1 kΩ (both the EEPROM and the camera sink
  ≥3 mA, so ≥1 kΩ is safe) and re-test. If the failure point moves up, it was
  rise-time, not layers.
- **Shorten the Qwiic cable** / unchain extra devices and re-test. If the failure
  point moves up, it was cable capacitance, not layers.
- **The crosstalk probe** (phase 4) is the one software-observable signature that
  a reference plane actually fixes: if the error rate rises *only* when the
  adjacent pin is switching, that points at crosstalk/return-path — i.e. at
  layers. If it doesn't move, there's no software evidence more layers would help.

Anything beyond that needs a scope on SDA/SCL: measure the 30–70 % rise time and
confirm the lines cross V_IH (0.7·V_DD ≈ 2.31 V) before the master samples. The
software narrows the question; a scope answers it. **Bottom line for the
designer:** at 4.7 kΩ the bus is comfortable at 133 kHz, already marginal by
400k, and out-of-spec at 1M *regardless of layer count* — so the layer decision
should be made against deconvolved variables (pull-up, cable, crosstalk), not a
single blended pass/fail.

---

## Appendix: getting a real frequency sweep

If the designer truly wants the failure-cliff-vs-frequency curve, the bus has to
be driven at variable speed. Two paths, neither needed for the soak above (both
were scoped out of this deliverable — ask and they can be built):

1. **SoftI2C over jumpers, no reflash.** Protogon breaks the slot's pins out to a
   2×10 header. Jumper the Qwiic SDA/SCL across to two of the *high-speed* pins
   (which go straight to ESP32 GPIO, bypassing the mux) and bit-bang
   `machine.SoftI2C(scl=…, sda=…, freq=…)` at a chosen speed. Pros: no firmware
   build. Cons: SoftI2C frequencies are approximate and capped at a few hundred
   kHz, and bit-bang jitter is itself a confound.

2. **Custom firmware, exact speeds.** Change `TILDAGON_HOST_I2C_FREQ` (or, better,
   patch the driver to accept a runtime `freq`) in
   `drivers/tildagon_i2c/tildagon_i2c.h` of `emfcamp/badge-2024-software`,
   rebuild with ESP-IDF, and flash via EMF's web flasher (reversible). Pros:
   exact 100k/400k/1M hardware speeds. Cons: a real toolchain build, and it
   reflashes a borrowed badge — get the owner's OK.

---

## Files

| File | What |
|---|---|
| `protogon_thermal_test.py` | the badge-side diagnostic — run with `mpremote run` |
| `host/render_frames.py` | turn the badge's `FRAME_B64:` line into a thermal PNG (Pillow) or `.pgm` (no deps) |
| `sim/fakehw.py` | fake `machine`/MLX90640/EEPROM for the host emulator |
| `sim/run_sim.py` | run the unmodified diagnostic on your PC against fake hardware |
| `README.md` | this file |

## Notes / gotchas

- **USB‑IN, data cable.** Wrong port = no device; charge-only cable = no device.
- One program owns the serial port at a time — close Thonny before `mpremote`.
- The MLX90640 calibration math for true °C is *not* included; the ASCII/PNG
  images are raw, uncalibrated ADC (hot = bright), which is all you need to prove
  the camera and bus work. For real temperatures, vendor the MIT-licensed
  `michael-sulyak/micropython-mlx90640` driver.
- Keep the camera at ≤4 Hz refresh: at 133 kHz a full frame read is ~123 ms, so
  faster refresh rates overwrite-race. The script uses 2 Hz.
- If the borrowed badge is on firmware 1.6.0, low-speed eGPIO is buggy — this
  tool only uses I²C and high-speed pins, so it's unaffected.
