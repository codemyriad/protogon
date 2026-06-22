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

### Regenerating the board

`generate_protogon.py` transforms the official EMF hexpansion board into this one,
so it needs two things that are **not** committed to this repo:

1. **KiCad's `pcbnew` Python module** on the path (run with the Python that ships
   with KiCad, e.g. KiCad 9's bundled interpreter).
2. **The upstream badge hardware**, cloned into `_upstream_badge_2024_hardware/`
   at the repo root (gitignored — the generator reads
   `_upstream_badge_2024_hardware/hexpansion/hexpansion.kicad_pcb`):

   ```
   git clone https://github.com/emfcamp/badge-2024-hardware.git \
     _upstream_badge_2024_hardware
   # pin to the reviewed revision for reproducibility:
   git -C _upstream_badge_2024_hardware checkout 33ff848
   ```

Then, from the repo root:

```
python3 tools/generate_protogon.py          # rewrites codemyriad-protogon.kicad_pcb
```

After regenerating, re-export the fabrication outputs with `kicad-cli` (Gerber/drill
zip, DRC report, STEP) so `fabrication/` and `drc-report.txt` stay in sync with the board.

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

### Accurate GPU renders (Cycles)

For photoreal stills and loops, render with **Cycles path tracing** instead of the
default EEVEE rasterizer:

```
blender -b -P ../tools/render_protogon_blender.py -- --engine cycles \
  --model renders/model/codemyriad-protogon.glb --outdir renders/blender \
  --top-texture renders/texture/top-surface-clean.png \
  --bottom-texture renders/texture/bottom-surface-clean.png
```

`--engine cycles` path-traces on the GPU (OptiX on NVIDIA, auto-falling back to
CUDA, then CPU) and denoises with **OpenImageDenoise** by default. The OptiX
*denoiser* fails to initialise on some driver/GPU combinations (observed on an
RTX 5060 / Blackwell with Blender 4.5), so OIDN is the default — path tracing
still runs on the GPU. Useful flags: `--poster-only` (fast single-frame preview),
`--samples N` (quality vs. speed, default 128 for Cycles), `--gpu-backend`,
`--denoiser`.

To render on a remote GPU box and pull the finished poster/MP4/GIF/contact sheet
back into the repo in one step:

```
tools/render-on-roy.sh                 # defaults to host roy.wye.it
SAMPLES=256 tools/render-on-roy.sh myhost
```

On an RTX 5060 a 1280×720 / 128-spp poster renders in ~4 s; a full 96-frame loop
is roughly a 6-minute GPU job.

## Notes

The project includes local footprint libraries copied into this folder so KiCad can run DRC without depending on a global KiCad library setup.

The board outline and connector footprint are derived from the official EMF badge 2024 hexpansion template. See `CERN-OHL-P-2.0.txt` for the copied license text.

Production pricing notes and a reusable quote recipe are stored one directory up:

- `../PRODUCTION-PRICING.md`
- `../QUOTE-RECIPE.json`
