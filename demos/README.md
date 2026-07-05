# Tildagon badge demos

Fourteen tiny, high-effect demos for the EMF Tildagon badge's round 240×240
screen — vector primitives, coarse grids and small particle systems rather than
brute-force per-pixel effects, which is what the badge's MicroPython
`update(delta)` / `draw(ctx)` model actually rewards. They come straight off the
shortlist in the design brief.

Each demo is a **standalone, unmodified badge app** (`demos/<name>/app.py`, a
`class … (app.App)` with `__app_export__`). Names are the numbers, spelled how
they sound: `uan`(1), `ciu`(2), `tri`(3), `for`(4), `faiv`(5), `sics`(6),
`seven`(7), `eit`(8), `nain`(9), `ten`(10), `ileven`(11), `twelv`(12),
`thurteen`(13), `forteen`(14).

## The demos

| # | name | what it is | controls (all: **CANCEL** exits) | LEDs |
|---|------|-----------|----------------------------------|:----:|
| 1 | [`uan`](uan/uan.gif) | **Tixy grid** — one formula drives a 16×16 dot field | LEFT/RIGHT formula · UP/DOWN speed | |
| 2 | [`ciu`](ciu/ciu.gif) | **Moiré rings** — two drifting ring families interfere | RIGHT circles↔hexagons | |
| 3 | [`tri`](tri/tri.gif) | **Qix tracer** — bouncing points with a fading trail | CONFIRM add point · RIGHT palette | ● |
| 4 | [`for`](for/for.gif) | **IMU starfield** — tilt steers the drift | tilt (WASD in sim) · UP/DOWN warp | ● |
| 5 | [`faiv`](faiv/faiv.gif) | **Polar tunnel** — concentric rings breathe | RIGHT colour scheme | |
| 6 | [`sics`](sics/sics.gif) | **Hex kaleidoscope** — one wedge stamped N-fold | CONFIRM randomise · RIGHT/LEFT symmetry | |
| 7 | [`seven`](seven/seven.gif) | **Hopalong** — strange-attractor point cloud | RIGHT/LEFT preset | |
| 8 | [`eit`](eit/eit.gif) | **Matrix rain** — glyph columns, round-cropped | RIGHT colour | |
| 9 | [`nain`](nain/nain.gif) | **Plasma tiles** — 16×16 sum-of-sines plasma | RIGHT palette | |
| 10 | [`ten`](ten/ten.gif) | **LED phase-lock** — screen + ring LEDs share one phase | RIGHT comet/pulse/rainbow | ● |
| 11 | [`ileven`](ileven/ileven.gif) | **Pipes grower** — orthogonal pipe runs on a grid | CONFIRM clear | |
| 12 | [`twelv`](twelv/twelv.gif) | **Cellular** — Life / Brian's Brain / cyclic | CONFIRM reseed · RIGHT rule | |
| 13 | [`thurteen`](thurteen/thurteen.gif) | **Drift lines** — braided spline ribbons | RIGHT/LEFT ribbon count | |
| 14 | [`forteen`](forteen/forteen.gif) | **Metaballs (lite)** — orbiting translucent blobs | RIGHT/LEFT blob count | |

Each folder's `.gif` is a render from the host simulator below (logic +
composition, not real badge colour/timing).

## Run them — host simulator (no badge, no dependencies)

`demos/sim/` is a pure-standard-library host simulator: it fakes the badge
runtime (`app`, `events`, `system`, `imu`, `tildagonos`, and a software `ctx`
rasteriser), drives `update()`/`draw()`, and writes PPM frames. It needs only
Python 3; `ffmpeg` (optional) turns the frames into a GIF.

```bash
python3 demos/sim/run.py --list           # list the demo names
python3 demos/sim/run.py uan --gif        # render uan -> demos/uan/uan.gif
python3 demos/sim/run.py for --gif --frames 60
python3 demos/sim/run.py all --gif        # re-render every demo
```

Useful flags: `--frames N`, `--every N` (updates between captured frames),
`--warmup N` (updates before capture — bump it for `seven`/`ileven`/`twelv`),
`--step-ms`, `--fps`, `--press "30:RIGHT,60:CONFIRM"` (script inputs),
`--no-round` (skip the round-screen mask). The LED ring is drawn around the
screen whenever a demo lights it.

This validates **logic and composition only** — real colours, frame rate and
the on-glass round crop still need the badge or the official simulator.

## Run them in the badge emulator (official SDL2 simulator, real ctx)

This is the badge emulator from `emfcamp/badge-2024-software`: a desktop window
running the real firmware + real uctx. Copy paste, from this repo's root:

```bash
# 1. get the emulator (once)
git clone --recursive https://github.com/emfcamp/badge-2024-software.git

# 2. install these demos into it (writes sim/apps/<Name>/ for each demo)
python3 demos/sim/install_to_official_sim.py badge-2024-software

# 3. launch the emulator
cd badge-2024-software/sim
cp config.py.default config.py            # buttons -> number keys, WASD = tilt
pipenv install                            # needs Python 3.10 + SDL2 (see below)
pipenv run python run.py                  # opens the launcher; pick a "Demos" entry
```

To skip the launcher and boot straight into one demo, pass `<Folder>.<Class>`
(both are the Capitalised name), e.g. `pipenv run python run.py Uan.Uan` or
`pipenv run python run.py For.For`.

**Controls in the emulator** (with `config.py` copied): `1`=UP `2`=RIGHT
`3`=CONFIRM `8`=DOWN `9`=LEFT `0`=CANCEL — or click the on-screen button dots.
**W/A/S/D** tilt the accelerometer (steers the `for` starfield). The ring LEDs
render around the screen (used by `tri`, `for`, `ten`).

**Prereqs:** the sim pins **Python 3.10** (not newer) and needs **pipenv** and
**SDL2** (`pip install --user pipenv`; on Linux the pygame wheel usually bundles
SDL2, else `sudo apt install libsdl2-2.0-0 libsdl2-image-2.0-0
libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0`). `install_to_official_sim.py` handles
the app wiring: it writes each demo into `sim/apps/<Name>/` with the
`metadata.json` + `__init__.py` the launcher expects, Capitalising folder/class
names so the `for` demo becomes an importable `For` (a bare `for` package can't
be imported).

Re-run step 2 any time you edit a demo to re-sync it into the emulator.

## Run them — on a real badge

Each `app.py` is a normal badge app. Drop a folder into your badge over
`mpremote` (with a `tildagon.toml`/`metadata.json`), publish through the app
store, or ship one on a hexpansion EEPROM (that's Protogon's day job — see the
sibling `app/` and `eeprom-image/` branches). The demos only use documented
APIs and clean up after themselves (the LED demos hand the ring back to the
system pattern service on exit).

## Porting notes (verified against emfcamp/badge-2024-software)

These are the facts the demos were written against — handy if you fork one:

- **Screen** is 240×240, **origin at the centre** (coords −120..+120), angles in
  radians. Clear each frame with `ctx.rgb(0,0,0).rectangle(-120,-120,240,240).fill()`.
- **`update(delta)`**: `delta` is **milliseconds**. Returning **`False` skips
  the redraw**; return `True`/`None` to draw. An app starts backgrounded — emit
  `RequestForegroundPushEvent(self)` once (guarded by a flag) to take the screen.
- **`ctx`** is uctx (a subset in the sim). Chainable draw/colour/transform calls
  return `self`; **properties** (`line_width`, `font_size`, `text_align`,
  `global_alpha`) are *assigned*, never read back. Pass colours as **0.0–1.0
  floats** (real uctx does not clamp). There is **no `rect` alias** — use
  `rectangle`. `scale(x, y)` needs both args.
- **LEDs** are 1-indexed `tildagonos.leds[1..12] = (r,g,b)` (0–255) then
  `.write()`. A system service owns the ring, so emit **`PatternDisable()`**
  before driving it and **`PatternEnable()`** when you leave (the `tri`/`for`/
  `ten` demos do exactly this).
- **IMU**: `import imu; imu.acc_read()` → `(x,y,z)` m/s² (dummy in the sim,
  WASD-driven). Wrap reads in `try/except (AttributeError, OSError, Exception)`
  and fall back — some IMU functions exist only on hardware, others only in the
  sim (`for` shows the pattern).

## Layout

```
demos/
  sim/
    tildagon_sim.py            fake badge runtime + software ctx rasteriser
    run.py                     CLI: render a demo (or all) to frames/GIF
    install_to_official_sim.py drop the demos into the SDL2 simulator
  <name>/app.py                one standalone badge app per demo
  <name>/<name>.gif            a host-sim render of it
```
