# Code Myriad Protogon

Code Myriad themed protoboard hexpansion for the EMF 2024 Tildagon/Spaceagon connector.

This revision is a bare protoboard functional equivalent inspired by JakeW's Protoboard Hexpansion. It intentionally omits the earlier LED and switch concept.

## Current Status

- KiCad DRC: clean, with 0 violations, 0 unconnected pads, and 0 footprint errors.
- Physical gate: test the connector tab and insertion fit against a 2024 badge before quantity order.
- Detect pin: `/HEXP_DET` is hard-tied to `/GND`.
- Work area: integrated 10 x 14 matrix on 2.54 mm pitch (120 usable proto pads; the 20 cells at columns 0-1, rows 2-11 are taken by the J2 header).
- Breakout: official 2 x 10 J2 pinout integrated into columns 0-1, rows 2-11. J2 pad 11 (upstream `/HEXP_DET`) carries `/GND` here, since the detect line is grounded.
- Rails: top row `/3V3`, bottom row `/GND`.

> Source of truth: `codemyriad-protogon.kicad_pcb` is generated programmatically by `../tools/generate_protogon.py` and is the authoritative netlist. `codemyriad-protogon.kicad_sch` is a retained copy of the upstream reference schematic (it still describes the upstream LED/jumper variant and is not in parity with this PCB) — do not treat it as the design source.

## Fabrication Settings

Use the generated Gerber zip as the order source:

`fabrication/codemyriad-protogon-fab.zip`

Recommended fab options:

- Layers: 2
- Thickness: 1.0 mm FR4
- Soldermask: black
- Silkscreen: white
- Surface finish: ENIG
- Edge connector bevel: none unless the fab confirms it improves fit for this tab geometry
- Copper weight: standard 1 oz

## Generated Outputs

Board + fabrication (from `../tools/generate_protogon.py` via `pcbnew`, plus `kicad-cli`):

- Fabrication Gerber/drill zip: `fabrication/codemyriad-protogon-fab.zip`
- DRC report: `drc-report.txt`
- STEP model: `fabrication/step/codemyriad-protogon.step`

Looping turntable render (from `../tools/render_protogon_blender.py`, see below):

- Poster still: `renders/blender/protogon-loop-poster.png`
- Loop MP4: `renders/blender/protogon-loop.mp4`
- Loop GIF: `renders/blender/protogon-loop.gif`
- Contact sheet: `renders/blender/protogon-loop-contact.jpg`

Static board renders (produced with `kicad-cli pcb render`; not yet scripted):

- Front render: `renders/top.png`
- Back render: `renders/bottom.png`

## Regenerating the Loop Render

`../tools/render_protogon_blender.py` renders a seamless, constant-angular-velocity
loop of the board and emits the poster, MP4, GIF, and contact sheet in one pass
(GIF/contact need `ffmpeg` on `PATH`). It runs on Blender 4.2-5.0:

```
blender -b -P ../tools/render_protogon_blender.py -- \
  --model renders/model/codemyriad-protogon.glb \
  --outdir renders/blender \
  --top-texture renders/texture/top-surface-clean.png \
  --bottom-texture renders/texture/bottom-surface-clean.png
```

The loop is 96 frames at 24 fps (4.0 s). The GIF is derived by **integer**
decimation (every 2nd frame) and encoded at 12.5 fps so every frame has an
identical 8-centisecond delay — this keeps the motion judder-free. Avoid
re-encoding the GIF at a frame rate that is not an integer divisor of the source
fps (e.g. 18 fps from a 24 fps source), which drops frames unevenly and reintroduces
a periodic stutter.

## Notes

The project includes local footprint libraries copied into this folder so KiCad can run DRC without depending on a global KiCad library setup.

The board outline and connector footprint are derived from the official EMF badge 2024 hexpansion template. See `CERN-OHL-P-2.0.txt` for the copied license text.

Production pricing notes and a reusable quote recipe are stored one directory up:

- `../PRODUCTION-PRICING.md`
- `../QUOTE-RECIPE.json`
