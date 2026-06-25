# Review handoff — Qwiic + EEPROM hexpansion

Detailed appendix to [README.md](README.md). For an experienced PCB/DFM reviewer: the verified state so you don't re-derive it, the traps in the repo, and the calls that are yours. The board-specific job scope is in the README; this is the depth.

## What it is

EMF 2024 Tildagon **hexpansion** protoboard, 2-layer. Base: 10×14 proto grid (PROTO1), badge edge connector (J1), 2×10 breakout header (J2). Added **I²C identification block**: U1 EEPROM, C1 decoupling, R1/R2 pull-ups, J3 Qwiic/STEMMA-QT on a rounded "ear" off the right rim. The badge reads the EEPROM to identify the hexpansion and auto-install its app.

Fab spec: **2-layer · 1.0 mm FR4 · ENIG · black mask · white silk · 1 oz Cu · no edge bevel.**

## Two boards — which is which

- [`../codemyriad-protogon.kicad_pcb`](../codemyriad-protogon.kicad_pcb) — **base board, the one to work from.** Proven outline + edge connector + proto grid + breakout header. No SMD parts.
- `codemyriad-protogon-qwiic.kicad_pcb` (this folder) — **the LLM's attempt. Reference only.** Its ear and EEPROM placement are the things you're being hired to do properly. Footprints are embedded, so it opens and DRCs without the libs.

Footprint libs (`*.pretty`, `fp-lib-table`) are at the repo root — harmless lib warnings result. The base board's fab package in [`../fabrication/`](../fabrication/) is gerbers + drill only (no BOM, no centroid) — a folder-structure template, not an assembly template.

## Verified state — don't re-derive

**LLM board, live `kicad-cli pcb drc`** (not any saved report): 0 errors, 3 warnings (silk-over-copper on C1; lib-not-in-config on J1; lib-mismatch on J2 — all benign), **0 unconnected.** The bus is routed (12 vias, 132 segments; SDA 13, SCL 14, 3V3 22, GND 51 tracks). *Copper continuity through layer changes is unverified* — that's on you to check, and vias landing inside proto holes is a real risk given the placement.

**EEPROM net intent** (already in the LLM board's pad-nets, as a reference for what you're reproducing): U1 pins 1,2,3,4,7 → GND (A0/A1/A2 + VSS + **WP** → address **0x50**, write-enabled), pin5→SDA, pin6→SCL, pin8→3V3. C1 = 3V3/GND. R1 = SDA/3V3, R2 = SCL/3V3 (both 10 k). J3 = 1:GND 2:3V3 3:SDA 4:SCL, shell→GND.

**Parts** (all SMD, top/F.Cu): U1 **CAT24C512** SOIC-8; R1/R2 **10 k 0603**; C1 **100 n 0603**; J3 **JST SM04B-SRSS-TB** (side-entry). J1/J2/H1/H2/PROTO are THT/mechanical. Real MPNs + LCSC in [`codemyriad-protogon-qwiic-bom.csv`](codemyriad-protogon-qwiic-bom.csv) — trust it over any schematic-generated BOM.

## Traps in the repo — read before you start

1. **No `.rpt` is tracked, and any saved DRC report is stale.** Re-run DRC yourself; don't trust a saved file.
2. **The "open" board outline is intentional.** Edge.Cuts has a ~12 mm gap on the left edge between (100.25, 94.0) and (100.25, 106.0) — that's the **hexpansion connector mouth** where the badge tongue inserts. The base board has byte-identical endpoints. **Do not close it.**
3. **DRC runs against a weakened ruleset.** `.kicad_pro` has most minimums set to 0.0; only the `Default` netclass (track 0.25, clearance 0.2, via 0.8/0.4 mm) is enforced. A "clean" DRC here is weaker than it looks — re-run against your fab's real capability profile.
4. **Schematic is the old upstream LED/jumper variant** — has D1/JP1 the PCB lacks, missing J3/U1/C1/R2, R1 value is `R` not `10k`. Either reconcile and get ERC clean, or formally make the PCB the source of truth and hand-maintain the parts list. Do **not** run Update-PCB-from-Schematic without resyncing first. Record which you chose.

## The placement problem (the core task)

The LLM did two things badly, and fixing them is the main job:

- **The ear.** J3 sits on a ~6 mm rounded tab bolted off the right rim. Whether that's even the right answer (vs. a different connector, a different edge, no ear) is open. If an ear stays, it must clear a populated neighbour and the cable must exit outward.
- **The EEPROM block.** U1/R1/R2/C1 are dumped in the dead centre of the proto grid, eating holes and silk. They need to be one cleanly-grouped, omittable block that leaves the bare board a full, clean grid.

Both are in the LLM board for reference only. Start from the base board and place them properly.

## Calls that are yours — the review

**Electrical (DRC can't see any of this)**
- [ ] 10 k pull-ups correct for total bus C (badge side + EEPROM + downstream Qwiic + cable) at 400 kHz?
- [ ] CAT24C512 (512 kbit): addressing doesn't perturb the firmware's `0x50–0x57` scan; `0x77` is reserved. (Premise already verified against `badge-2024-software` — see [DERISK-FINDINGS.md](DERISK-FINDINGS.md) — but confirm on your part.)
- [ ] WP hard-tied to GND (always writable) — accept, or want a solder-jumper to protect the ID block after provisioning?

**Mechanical / fit — needs a real 2024 badge**
- [ ] Edge-connector fingers: is **no bevel** actually right, or do they need a lead-in chamfer?
- [ ] J3 ear clears a **fully populated** badge + cable bend? (See README fit check.)
- [ ] Connector-mouth slot width / internal corner radius vs your fab's router bit.

**DFM / fab — file-checkable**
- [ ] Solder-mask dam between SOIC-8 pins (1.27 mm) and the 0603 pads vs fab minimum (zeroed rule hides this).
- [ ] ENIG ring/pad size on the 140 PTH proto holes for repeated hand-rework.
- [ ] Footprint land patterns vs the **exact purchased** JST + EEPROM MPNs (pin-1, polarity, courtyard).
- [ ] Panelisation / breakaway rail for the irregular outline?

**After routing**
- [ ] Review the actual routing: via placement vs hand-solder proto pads, SDA/SCL return paths (2-layer, no pour).
- [ ] Re-run DRC under a real ruleset; save a fresh report.

**Out of scope here (flag if relevant):** badge firmware THEX/LittleFS write path vs the chosen part; H1/H2 are netless (not GND-tied) by current design.

## Definition of done

1. Fresh DRC: **0 errors, 0 unconnected**, under a realistic ruleset.
2. Bus routed to every block pad; EEPROM `0x50` + WP-GND realised in copper.
3. Physical fit confirmed on a real badge (tab seats, ear clears neighbours, cable exits radially).
4. PCB↔schematic decision recorded (PCB-as-source, or resynced + ERC clean).
5. Fab outputs regenerated fresh and timestamped after the last PCB save: gerbers (explicit `--layers` list, not `--board-plot-params`), drill, STEP, + zip; for assembly add a hand-authored BOM and a PCB-sourced centroid.
6. Order spec pinned: 2-layer · 1.0 mm FR4 · ENIG · black mask · white silk · 1 oz · no bevel · **route the profile as-drawn (mouth + ear are intentional).**
