# Code Myriad Protogon — board

The KiCad design, fabrication package, and renders for the Code Myriad Protogon
protoboard hexpansion. Project rationale, credits (JakeW's protohex), and EMF badge
links are in the [top-level README](../README.md).

## Current status

- **KiCad DRC:** clean — 0 violations, 0 unconnected pads, 0 footprint errors.
- **Proto field:** 10×14 matrix on 2.54 mm pitch. All holes are PTH pads with an exposed
  ENIG gold ring (soldermask-opened) — every hole is solderable.
- **Breakout:** the official 20-pad edge-connector pinout is broken out to a 2×10 header
  (J2) integrated into columns 0–1, rows 2–11. The 120 remaining cells are free proto pads.
- **Rails:** top row `/3V3`, bottom row `/GND`.
- **Detect pin:** `/HEXP_DET` is hard-tied to `/GND` (J2 pad 11 carries `/GND`).
- **Physical gate:** test the connector tab / insertion fit against a real 2024 badge
  before any quantity order.

> **Source of truth:** `codemyriad-protogon.kicad_pcb` is generated programmatically by
> [`../tools/generate_protogon.py`](../tools/generate_protogon.py) — don't hand-edit it.
> `codemyriad-protogon.kicad_sch` is a retained copy of the upstream reference schematic
> (still the upstream LED/jumper variant, **not** in parity with this PCB) — not the design source.

## Fabrication

Order source: **`fabrication/codemyriad-protogon-fab.zip`** (Gerbers + drill).

Recommended fab options: 2 layers · 1.0 mm FR4 · black soldermask · white silkscreen ·
**ENIG** surface finish · no edge-connector bevel · 1 oz copper.

Other generated outputs:
- DRC report: `drc-report.txt`
- STEP model: `fabrication/step/codemyriad-protogon.step`
- KiCad raytraced reference renders (ground-truth stackup colors): `renders/kicad/`

## Regenerating the board

`generate_protogon.py` transforms the official EMF hexpansion board into this one, so it
needs two things that are **not** committed here:

1. **KiCad's `pcbnew` Python module** (run with KiCad 9's bundled interpreter, or a Python
   that can `import pcbnew`).
2. **The upstream badge hardware**, cloned into `_upstream_badge_2024_hardware/` at the
   repo root (gitignored — the generator reads `…/hexpansion/hexpansion.kicad_pcb`):

   ```
   git clone https://github.com/emfcamp/badge-2024-hardware.git _upstream_badge_2024_hardware
   git -C _upstream_badge_2024_hardware checkout 33ff848   # pin to the reviewed revision
   ```

Then, from the repo root:

```
python3 tools/generate_protogon.py        # rewrites codemyriad-protogon.kicad_pcb
```

After regenerating, re-export the fabrication outputs with `kicad-cli` (gerbers, drill,
STEP, DRC report) and the GLB model so `fabrication/`, `drc-report.txt`, and
`renders/model/` stay in sync with the board.

## Renders

The photoreal turntable loop is produced by
[`../tools/render_protogon_blender.py`](../tools/render_protogon_blender.py) (Cycles
path-tracing on a GPU; needs `ffmpeg` for the MP4/GIF/contact sheet). The easiest path is
the remote-GPU wrapper, which syncs up, renders, and pulls the results back:

```
tools/render-on-roy.sh                       # full loop -> renders/blender/
SAMPLES=256 tools/render-on-roy.sh myhost     # knobs: SAMPLES/WIDTH/HEIGHT/FRAMES/XRAY/OUTSUB
```

Key points of the pipeline:

- **Real geometry, real materials:** renders the actual GLB (copper/pads/silk/mask), with
  ENIG gold (metallic + warm specular tint), a coated black soldermask, matte white silk,
  and a slightly translucent FR4 edge.
- **Lighting:** a studio HDRI (`renders/hdri/`) for believable reflections + soft area
  lights, with the **EMF-sign photo** (`renders/bg/`) composited as the backdrop.
- **Color:** AgX for the beauty render; add `--standard-view` for a literal-color check
  against the `kicad-cli` reference and physical swatches.
- **GPU/denoise:** OptiX path-tracing with OpenImageDenoise (the OptiX *denoiser* fails to
  init on RTX 5060 / Blender 4.5, so OIDN is the default). `--poster-only` for a fast still;
  `--xray` makes the soldermask translucent to inspect copper routing.

The loop is **192 frames at 24 fps (8.0 s)**. The GIF is integer-decimated (every 2nd
frame) and encoded at 12.5 fps so each frame gets an identical 8-centisecond delay —
keeping the motion judder-free. Don't re-encode the GIF at a frame rate that isn't an
integer divisor of the source fps.

## Notes

- Local footprint libraries (`*.pretty`) are copied into this folder so KiCad can run DRC
  without a global library setup.
- The board outline and edge-connector footprint derive from the official EMF badge 2024
  hexpansion template; see `CERN-OHL-P-2.0.txt` for the license.
- Pricing and the reusable quote recipe live in [`../docs/`](../docs/)
  (`PRODUCTION-PRICING.md`, `QUOTE-RECIPE.json`).
