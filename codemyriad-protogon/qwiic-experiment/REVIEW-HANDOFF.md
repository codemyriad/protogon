# Review handoff — codemyriad-protogon-qwiic (Qwiic + EEPROM hexpansion)

For an experienced PCB/DFM reviewer. Goal: take this from "design done on screen" to
**ready to order**. This brief gives you the verified state so you don't re-derive it, the
traps in the repo, and the calls that are yours to make.

## What it is

EMF 2024 tildagon **hexpansion** protoboard, 2-layer. A 10×14 proto grid (PROTO1), the badge
edge connector (J1), a 2×10 breakout header (J2), plus an added **I²C identification EEPROM
cluster**: U1 EEPROM, C1 decoupling, R1/R2 pull-ups, and J3 Qwiic/STEMMA-QT on a rounded
"ear" off the right rim. The badge identifies the hexpansion and installs software off the EEPROM.

Intended fab spec (from the PCB stackup + title block): **2-layer · 1.0 mm FR4 · ENIG ·
black mask · white silk · 1 oz Cu · no edge bevel.**

## Files / where things live

- `codemyriad-protogon-qwiic.kicad_pcb` — **the source of truth.** All footprints embedded.
- `codemyriad-protogon-qwiic.kicad_sch` — **stale, do not trust** (see traps).
- `codemyriad-protogon-qwiic.kicad_pro` — design rules (note: minimums largely zeroed, see traps).
- `codemyriad-protogon-qwiic-drc.rpt` — **stale, do not trust** (see traps).
- `README.md` — the brief for this job (the goal, which choices are real vs accidental, the honest state, the scope, and what to deliver). **Start there**; this file is the detailed appendix it links to.
- Footprint libs (`*.pretty`, `fp-lib-table`) are at the **repo root**, one level up — harmless
  lib warnings result (footprints are embedded in the PCB, so export/DRC work regardless).
- No fab outputs exist for this variant yet. The base board's package
  (`../fabrication/`) is **gerbers + drill only — no BOM, no centroid** — use it as the
  folder-structure template, not as an assembly template.

## Verified current state — you don't need to re-derive this

- **Live `kicad-cli pcb drc`** (not the saved report): **0 errors, 3 warnings**
  (silk-over-copper on C1; lib-not-in-config on J1; lib-mismatch on J2 — all benign),
  **20 unconnected items.**
- EEPROM net intent is already in the footprint pad-nets (just not yet in copper):
  U1 pins **1,2,3,4,7 → GND** (A0/A1/A2 + VSS + **WP**, i.e. address **0x50**, write-enabled),
  pin5→SDA, pin6→SCL, pin8→3V3. C1 = 3V3/GND. R1 = SDA/3V3, R2 = SCL/3V3 (both 10 k).
  J3 = 1:GND 2:3V3 3:SDA 4:SCL, shell→GND.
- Parts (all SMD, all on **top/F.Cu**): U1 **CAT24C512** SOIC-8 (alt: **ZD24C64A-XGMT**,
  footprint/wiring-compatible, EMF-tested), R1/R2 **10 k 0603**, C1 **100 n 0603**,
  J3 **JST SM04B-SRSS-TB** (horizontal). J1/J2/H1/H2/PROTO are THT/mechanical.

## The one hard blocker

**The I²C + power bus is unrouted past J2.** `/SDA` and `/SCL` copper runs only J1↔J2; it
never reaches U1, R1, R2, C1, or J3 (same-net gaps 2–29 mm → the 20 unconnected items). The
firmware-verified `0x50` strap, WP-grounding, pull-ups, and decoupling exist on paper but **not
in copper.** This is GUI interactive routing (kicad-cli can't route). README has a lane recipe:
SDA/SCL on **B.Cu** in the inter-row lanes y≈99.98 / 97.44, column gaps x≈135.66 / 138.20,
J2 pad7/9 → cluster → J3 pad3/4; 3V3 up the right margin to the top rail, GND down to the bottom rail.

## Traps in the repo — read before you start

1. **`…-drc.rpt` is stale** (32 violations + 7 unconnected, timestamp 15:51 vs PCB saved 21:28).
   The shorts and solder-mask bridges it lists were **already fixed**. Re-run DRC yourself.
2. **README says "0 DRC errors, placement final and clean" — false.** The bus is unrouted.
   Neither the README nor the stale .rpt is authoritative; a fresh DRC is.
3. **The "open" board outline is intentional.** Edge.Cuts has a ~12 mm gap on the left edge
   between (100.25, 94.0) and (100.25, 106.0) — that's the **hexpansion connector mouth** where
   the badge tongue inserts. The shipped base board (`../codemyriad-protogon.kicad_pcb`) has
   byte-identical endpoints. **Do not close it.**
4. **DRC is running against a weakened ruleset.** `.kicad_pro` has most minimums set to 0.0;
   only the `Default` netclass (track 0.25, clearance 0.2, via 0.8/0.4 mm) is enforced. A "clean"
   DRC here is weaker than it looks — re-run against your fab's real capability profile.
5. **Schematic is the old upstream LED/jumper variant** — has D1/JP1 the PCB lacks, missing
   J3/U1/C1/R2, R1 value is `R` not `10k`. A schematic-generated BOM is wrong. Treat the **PCB
   as source of truth**; do **not** run Update-PCB-from-Schematic without resyncing first.

## Calls that are yours — the review

**Electrical (DRC can't see any of this)**
- [ ] 10 k pull-ups correct for total bus C (badge mux + EEPROM + downstream Qwiic + cable) at 400 kHz?
- [ ] CAT24C512 (512 kbit): confirm its addressing doesn't perturb the firmware's `0x50–0x57` scan; `0x77` is reserved by the badge mux.
- [ ] WP hard-tied to GND (always writable) — accept, or want a jumper/safeguard for the ID block?

**Mechanical / fit — needs a real 2024 badge**
- [ ] Edge-connector fingers: is **no bevel** actually right, or do they need a lead-in chamfer?
- [ ] J3 "ear" (outline out to x=154, new vs base) clears a **fully populated** badge + cable bend?
- [ ] Connector-mouth slot width / internal corner radius vs your fab's router bit.

**DFM / fab — file-checkable**
- [ ] Solder-mask dam between SOIC-8 pins (1.27 mm) and the 0603 pads vs fab minimum (zeroed rule hides this).
- [ ] ENIG ring/pad size on the 140 PTH proto holes for repeated hand-rework.
- [ ] Footprint land patterns vs the **exact purchased** JST + EEPROM MPNs (pin-1, polarity, courtyard).
- [ ] Panelization / breakaway rail for the irregular outline?

**After routing**
- [ ] Review the actual routing: via placement vs hand-solder proto pads, SDA/SCL return paths (2-layer, no pour).
- [ ] Re-run DRC under a real ruleset; **overwrite the stale `.rpt`.**

**Out of scope here (flag if relevant):** badge firmware THEX/LittleFS write path vs the chosen part; H1/H2 are netless (not GND-tied) by current design.

## Definition of done

1. Fresh DRC: **0 errors, 0 unconnected**, under a realistic ruleset.
2. Bus routed to every cluster pad; EEPROM `0x50` + WP-GND realised in copper.
3. Physical fit confirmed on a real badge (tab seats, ear clears neighbours, cable exits radially).
4. PCB↔schematic decision recorded (PCB-as-source, or resynced + ERC clean).
5. Fab outputs regenerated fresh and timestamped after the last PCB save: gerbers (explicit
   `--layers` list, not `--board-plot-params`), drill, STEP, + zip; for assembly add a
   hand-authored 5-line BOM and a PCB-sourced centroid.
6. Order spec pinned: 2-layer · 1.0 mm FR4 · ENIG · black mask · white silk · 1 oz · no bevel ·
   **route the profile as-drawn (mouth + ear are intentional).**
