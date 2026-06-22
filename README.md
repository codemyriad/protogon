# Code Myriad Protogon — EMF badge hexpansion (order prep)

Working repository for the **Code Myriad Protogon**: a small, bare protoboard
"hexpansion" that slots into the EMF Camp badge (2024 *Tildagon* / 2026
*Spaceagon*) 20-pad edge connector. It's a sponsor giveaway breakout — it just
has to slot in and make reliable electrical contact (3V3 + I²C). This repo holds
the board design, the scripts that generate it, and the cost research used to
decide how and where to order it.

## Repository layout

| Path | What it is |
| --- | --- |
| [`codemyriad-protogon/`](codemyriad-protogon/) | The KiCad design + fabrication outputs + renders. See its [README](codemyriad-protogon/README.md) for the board detail. |
| `codemyriad-protogon/fabrication/codemyriad-protogon-fab.zip` | **The order source** — Gerbers + drill, ready to upload to a fab. |
| [`tools/`](tools/) | `generate_protogon.py` (generates the `.kicad_pcb` — the source of truth) and `render_protogon_blender.py`. |
| [`PRODUCTION-PRICING.md`](PRODUCTION-PRICING.md) | Captured quotes & supplier comparison (JLCPCB, Leiton, CONTAG, ANDUS). |
| [`QUOTE-RECIPE.json`](QUOTE-RECIPE.json) | Machine-readable quote recipe to reproduce/refresh those quotes. |
| [`CONTRACTOR-BRIEF.md`](CONTRACTOR-BRIEF.md) | Self-contained brief for a freelance PCB engineer (shareable). |
| `internal/` | Private hiring notes (strategy, outreach) — internal to Code Myriad. |
| `_upstream_badge_2024_hardware/` | Local clone of the official badge hardware for reference. **Not tracked** (see `.gitignore`); the bits we depend on are copied into `codemyriad-protogon/`. |

## Ordering — current state

- **Spec:** 2-layer FR4, **1.0 mm**, black soldermask, white silkscreen, **ENIG**
  (HASL forbidden), no edge bevel. Full spec in `CONTRACTOR-BRIEF.md` Part A.
- **DRC:** clean (0 violations / 0 unconnected / 0 footprint errors) — see
  `codemyriad-protogon/drc-report.txt`.
- **Gate before any quantity order:** the physical connector/insertion fit must
  be validated against a real 2024 badge first. See `PRODUCTION-PRICING.md`.
- **Deadline:** boards in Germany by **13 July 2026** (carried to the UK event
  16–19 July).

To refresh a quote, follow `QUOTE-RECIPE.json` (regenerate the Gerber zip first if
the board changed).

## Regenerating the board & renders

The `.kicad_pcb` is generated programmatically — don't hand-edit it. See
[`codemyriad-protogon/README.md`](codemyriad-protogon/README.md) for the exact
`generate_protogon.py` (via KiCad `pcbnew`) and `render_protogon_blender.py`
invocations.

## License

The hardware is licensed **CERN-OHL-P v2** (permissive) — see
[`codemyriad-protogon/CERN-OHL-P-2.0.txt`](codemyriad-protogon/CERN-OHL-P-2.0.txt).
The board outline and connector footprint derive from the official EMF 2024
badge hexpansion template.
