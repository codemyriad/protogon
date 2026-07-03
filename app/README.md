# Protogon thermal camera app

Plug an MLX90640 thermal camera into Protogon's Qwiic socket, insert Protogon
into the badge, and the badge screen becomes a **live heatmap**. The app lives
on the hexpansion's own tiny EEPROM, so it works on *any* badge: insert it and
the badge finds, mounts and launches the app by itself — nothing to install on
the badge first.

<img src="example-frame.png" width="240" alt="Thermal frame rendered by the simulator">

*(A frame rendered by the included simulator — a warm blob over a gradient.
Point the real camera at your face for the real thing. Hot = bright.)*

Written for beginners: if you have never touched a badge or MicroPython,
follow the steps top to bottom and you'll be fine.

---

## What you need

* An **EMF Tildagon badge** (2024 or 2026 firmware — both work), plus a USB-C
  **data** cable (a charge-only cable will silently not work).
* A **Protogon** hexpansion.
* An **MLX90640 thermal camera** with a Qwiic/STEMMA-QT connector (e.g.
  SparkFun SEN-14843) and a Qwiic cable.
* A laptop with Python 3. That's it — the one tool we use installs with:

  ```bash
  pip install --user mpremote
  ```

## Install it (one time, ~2 minutes)

1. **Plug things together:** camera → Qwiic cable → Protogon's Qwiic socket.
   Protogon → any badge slot. Note the **slot number**: slots count **1–6
   clockwise, starting from the upper-right slot**. Badge → laptop, using the
   badge's **USB-IN** port (it has two USB-C ports; the other one won't show
   up on your laptop).

2. **Check the P1 jumper is open** (nothing bridging its two pins). Open means
   the EEPROM can be written. Protogon ships open. (Shorting P1
   write-protects the EEPROM — useful *after* provisioning, see below.)

3. **Tell the script which slot you used:** if it's not slot 1, open
   `provision_protogon.py` and change `PORT = 1` at the top.

4. **From this `app/` directory, run:**

   ```bash
   mpremote cp app.py :protogon_app_payload.py + run provision_protogon.py
   ```

   This copies the app to the badge, then writes the hexpansion identity
   header, formats the EEPROM's little filesystem, installs the app into it,
   and verifies every step (it prints what it's doing as it goes).

5. **Reboot the badge:**

   ```bash
   mpremote reset
   ```

   The badge boots, pops up a **"Protogon"** notification, and the thermal
   viewer starts on its own. Wave a warm hand in front of the camera.

That's it. From now on it also works on any *other* badge: just insert
Protogon and the app launches.

> **Afterwards (optional):** short P1 with a jumper to write-protect the
> EEPROM, so nothing can corrupt the app in the field. Remove it again
> whenever you want to update the app.

## Everyday use

* **Insert** Protogon → app launches by itself (takes a second or two).
* **CANCEL button** → the viewer minimises back to the badge menu.
  Note: on current firmware a minimised hexpansion app may not appear in the
  launcher menu — **eject and re-insert Protogon** to bring it back.
* No camera plugged in? The screen tells you what to check, and it keeps
  looking — plug the camera in and it recovers by itself. Same if you unplug
  the camera while it's running.

The number at the bottom of the screen is the raw sensor range being mapped
to the palette. The image is **raw sensor counts, not degrees**: the Melexis
per-pixel calibration math is far bigger than the whole 8 KiB EEPROM, and for
"where is warm/cold" you don't need it.

## Try it without a badge

The simulator runs the exact `app.py` on your PC against a fake badge and a
fake, animated camera, and writes what the screen would show as image files:

```bash
cd sim
python3 run_app_sim.py               # writes thermal_000.png (or .ppm) ...
python3 run_app_sim.py --no-camera   # see the "check the Qwiic cable" screen
```

(`.png` needs Pillow — `pip install --user pillow`; without it you get `.ppm`
files, which most image viewers open fine.) Use it to iterate on the app —
palette, layout, logic — before touching hardware.

## Changing the app

1. Edit `app.py` (it's short and commented).
2. See it: `cd sim && python3 run_app_sim.py`.
3. Re-install **just the app** (keeps the header + filesystem): set
   `APP_ONLY = True` at the top of `provision_protogon.py`, then re-run the
   step-4 command.

### If it doesn't fit

The EEPROM is 64 **kilobit** = 8192 bytes. After the 32-byte header and
littlefs overhead, about **6.5 KB** remains, and the installer strips comment
lines from `app.py` (≈6 KB installed), leaving a few hundred bytes of headroom.
If you add real code you may hit the ceiling — the installer checks and tells
you rather than half-writing. Options: trim code, or (advanced) pre-compile
with `mpy-cross` to roughly halve the size — but a compiled `app.mpy` must
match the badge firmware's bytecode version, so it can break on firmware
updates; plain `app.py` never does.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mpremote: no device found` | Use the **USB-IN** port; use a **data** cable; close Thonny/other serial programs. |
| `no EEPROM found on port N` | Wrong `PORT` (count 1–6 clockwise from upper-right) or Protogon not fully seated. |
| `header did not stick` | The P1 jumper is shorted → EEPROM is write-protected. Remove it and re-run. |
| `this EEPROM already has a valid header` | It was provisioned before. `FORCE = True` rewrites everything, `APP_ONLY = True` just updates the app. |
| Badge boots but no app | Did you `mpremote reset` after provisioning? Eject/re-insert Protogon. Check the "Protogon" notification appears. |
| Screen says `no camera found` | Qwiic cable seated at both ends? Camera must be at I²C address 0x33 (the default). |
| `mpremote run` exits with `KeyboardInterrupt` | A known race with the badge UI — run the same command again. |
| Image looks like a checkerboard when things move fast | Normal: the camera measures half its pixels at a time (chess pattern). It settles when movement slows. |
| Weird colors / image frozen | Eject and re-insert Protogon; worst case re-run provisioning with `FORCE = True`. |

Still stuck? Run the bus diagnostic in [`../diagnostics/`](../diagnostics/) —
it tests the same EEPROM + camera at the I²C level and prints exactly what it
finds.

## How it works (for the curious)

* **The EEPROM** (ZD24C64A, 8 KiB) holds a 32-byte identity header (magic
  `THEX`, vendor/product id, friendly name, filesystem geometry) followed by
  a littlefs filesystem containing `app.py`. On insert, the badge reads the
  header, mounts the filesystem at `/hexpansion_<slot>`, imports `app.py` and
  launches the class it exports — straight from the EEPROM. This repo's
  provisioning script does what the badge firmware's own
  [`prepare_eeprom.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/scripts/prepare_eeprom.py)
  does, plus the single-transaction header write that Zetta EEPROMs like ours
  need ([issue #59](https://github.com/emfcamp/badge-2024-software/issues/59)),
  plus verification of every step.
* **The app** reads camera frames over the badge's 133 kHz I²C bus in small
  chunks (~26 ms each) so the badge UI never freezes, asks the camera for
  2 Hz refresh (a full frame is ~0.13 s of bus time — faster would clog the
  bus), drops any frame the sensor overwrote mid-read, and only redraws when
  a new frame arrives. Drawing merges
  same-colored horizontal runs into single rectangles (~250 instead of 768
  per frame) because the badge's vector renderer is slow.
* **VID/PID:** it ships with `vid=0xCAFE` (the community "open to everyone"
  vendor id) and `pid=0x7060`. If you make your own hexpansion, register a
  pid via an issue at
  [emfcamp/hexpansion-firmwares](https://github.com/emfcamp/hexpansion-firmwares).

## Files

| File | What |
|---|---|
| `app.py` | the badge app — installed onto the EEPROM |
| `provision_protogon.py` | writes header + filesystem + app to the EEPROM (run via `mpremote`) |
| `sim/run_app_sim.py` | run the app on your PC against a fake camera, renders frames |
| `example-frame.png` | a simulator-rendered frame (above) |
