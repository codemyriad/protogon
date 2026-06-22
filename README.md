# Code Myriad Protogon

A small, bare **protoboard "hexpansion"** that [Code Myriad](https://codemyriad.io)
is giving away at EMF Camp. It slots into the EMF badge's hexpansion port and breaks
the badge's I²C bus, 3V3 and GND out onto a solderable prototyping field, so a maker
can build their own add-on on the spot.

![Code Myriad Protogon, rendered in front of the EMF sign](codemyriad-protogon/renders/blender/protogon-loop-poster.png)

*Cycles/OptiX render of the board (black soldermask, ENIG gold, every proto hole
solderable). Animated turntable: [`protogon-loop.gif`](codemyriad-protogon/renders/blender/protogon-loop.gif)
· back side and routing in [`codemyriad-protogon/renders/`](codemyriad-protogon/renders/).*

## Why this exists (rationale)

The EMF Camp badge (2024 **Tildagon**, 2026 **Spaceagon** — same hexpansion interface)
has six slots for small ~1 mm "hexpansion" boards. We wanted a giveaway that is genuinely
useful, cheap enough to hand out in quantity, and reliable on the **first paid order**
(we're a software company and can't iterate on hardware at the event).

A **bare passive protoboard breakout** is the answer: lowest cost, lowest risk, no
assembly, nothing to go wrong electrically. It just has to slot in, make reliable contact,
and give people pads to solder to. Every hole has an exposed ENIG gold ring, the 20-pad
edge-connector pinout is broken out to a 2×10 header, and power rails run top (3V3) and
bottom (GND) — the rest of the field is yours.

## Credits

- **JakeW** — this design's form factor and proto-field approach are functionally
  inspired by his **Protoboard Hexpansion ("protohex")**.
  Site: <https://jakew.me> · on Tindie:
  <https://www.tindie.com/products/jakew/protoboard-hexpansion/>
- **EMF Camp** — the badge hardware, the hexpansion mechanical/electrical spec, and the
  KiCad template our board is derived from, released under CERN-OHL-P v2.
- **Poly Haven** — the CC0 studio HDRI used to light the product renders.

## EMF badge documentation

- Tildagon badge docs — <https://tildagon.badge.emfcamp.org/>
- Creating hexpansions (the spec we built to) —
  <https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/>
- Badge hardware (our upstream template) —
  <https://github.com/emfcamp/badge-2024-hardware>
- Badge documentation repo — <https://github.com/emfcamp/badge-2024-documentation>
- 2026 Spaceagon announcement —
  <https://blog.emfcamp.org/2026/05/28/tildagon-2026-spaceagon/>

## Repository layout

| Path | What |
| --- | --- |
| [`codemyriad-protogon/`](codemyriad-protogon/) | The KiCad design, fabrication outputs, and renders. See its [README](codemyriad-protogon/README.md) for board detail and how to regenerate. |
| [`tools/`](tools/) | `generate_protogon.py` (generates the board — the source of truth), `render_protogon_blender.py` + `render-on-roy.sh` (GPU renders), `svg_logo_to_silk.py` (logo → silk). |
| `_upstream_badge_2024_hardware/` | Local clone of the EMF badge hardware (reference; **not tracked** — see `.gitignore`). |
