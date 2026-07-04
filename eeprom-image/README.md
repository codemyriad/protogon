# Protogon EEPROM test + logo app

One `mpremote` command does two things:

1. **Tests the EEPROM on a produced board** — writes and verifies every byte,
   then confirms the flashed files read back exactly. Prints a plain
   **PASS** / **FAIL** for a test bench.
2. **Leaves a working demo** — the board shows the Codemyriad logo on the badge
   screen whenever it's inserted. A minimal, useful thing a bare Protogon can do.

<img src="logo-preview.png" width="200" alt="The Codemyriad logo as shown on the badge">

*(What the badge draws — the logo mark, white on black, decoded from the
632-byte `logo.dat`. This is the simulator's exact render.)*

The image is stored as a tiny 1-bit bitmap and drawn with plain rectangles, so
the app doesn't depend on the badge's image decoder — it works on any firmware,
and if the picture comes up clean, the EEPROM stored and returned every byte.

---

## What you need

* An **EMF Tildagon/Spaceagon badge** and a USB-C **data** cable.
* A **Protogon** with its EEPROM populated, in a badge slot.
* `pip install --user mpremote` on your laptop.

## Flash + test a board

1. Plug Protogon into a slot (note the number — **1–6 clockwise from the
   upper-right slot**) and the badge into your laptop's **USB-IN** port.
2. Make sure the **P1 jumper is open** (open = EEPROM writable; shorted =
   write-protected). If your slot isn't 1, set `PORT` at the top of
   `flash_logo.py`.
3. From this directory:

   ```bash
   mpremote cp app.py :logo_app_payload.py + cp logo.dat :logo_data_payload.dat + run flash_logo.py
   ```

   It prints each phase and ends with a banner:

   ```
   ############################################################
   #  RESULT: PASS -- EEPROM good, logo app flashed.
   ############################################################
   ```

   A **FAIL** banner names what went wrong (a bad cell address, a write-protect
   jumper, a payload that doesn't fit). On the production line: PASS = ship it.

4. `mpremote reset` (or re-insert Protogon). The badge shows a "Protogon"
   notification and the logo appears. Optionally short P1 to write-protect.

> **The cell test** writes two complementary patterns (0xAA/0x55) across all
> 8192 bytes and verifies them — a few seconds, catches stuck bits anywhere.
> Set `FULL_TEST = False` in `flash_logo.py` for a quick flash that only
> verifies the two files it writes.

## Try it without a badge

```bash
python3 sim/run_app_sim.py            # renders the screen to screen.png
python3 sim/run_app_sim.py --missing  # the "logo load failed" screen
```

It runs the real `app.py` against a fake badge and rasterizes what the screen
would show. (`.png` needs Pillow — `pip install --user pillow`; otherwise you
get `screen.ppm`.)

## Changing the image

`logo.dat` is generated from `tools/logo.svg` (a committed copy of the
Codemyriad logo). To regenerate or swap it:

```bash
python3 tools/make_logo.py                 # rebuild logo.dat from tools/logo.svg
python3 tools/make_logo.py --size 120      # crisper (bigger file)
python3 tools/make_logo.py --svg mine.svg  # a different simple logo
```

The tool takes only the mark on the **left** of the wordmark, squares it, and
renders it white-on-black at the chosen resolution. It needs only Pillow — the
few SVG paths are rasterized directly, no cairo/SVG library. The whole payload
(app + image) must fit the ~6.5 KB the EEPROM's filesystem holds; the default
100×100 logo is 632 bytes and the app ~3 KB, so there's plenty of room.

### logo.dat format

`PLG1` magic, a width byte, a height byte, then for each row: a count byte
followed by that many `(start, length)` pairs marking the white runs. Decoding
and drawing is a dozen lines — see `app.py`.

## Files

| File | What |
|---|---|
| `flash_logo.py` | run on the badge via `mpremote`: tests the EEPROM + flashes the app |
| `app.py` | the badge app — draws `logo.dat` on screen |
| `logo.dat` | the 1-bit logo (generated) |
| `tools/make_logo.py` | rebuild `logo.dat` from an SVG |
| `tools/logo.svg` | source Codemyriad logo |
| `sim/run_app_sim.py` | preview the app on a PC, no badge |
| `logo-preview.png` | the render shown above |
