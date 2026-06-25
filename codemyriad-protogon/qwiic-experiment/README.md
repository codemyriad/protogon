# Protogon Qwiic + EEPROM hexpansion

A small 2-layer KiCad board for review and finalisation. It's a [Tildagon](https://tildagon.badge.emfcamp.org/) [hexpansion](https://tildagon.badge.emfcamp.org/hexpansions/) — an add-on for the EMF 2024 badge — that combines a prototyping grid with an optional I²C identification EEPROM and a Qwiic/STEMMA QT connector.

The layout was produced with an LLM and has never been reviewed by a human PCB designer. You're being hired to be the first. Treat the file as a starting point, not a spec: most "decisions" in it aren't.

If you don't know Tildagon hexpansions, the load-bearing facts (pinout, mechanical limits, I²C/EEPROM mechanism, fab gotchas) are collected in [BACKGROUND.md](BACKGROUND.md), with primary sources linked at the bottom. The two short references that matter most:

- [Create a hexpansion](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/) — official pinout, 1 mm / ENIG / 32 mm flats, per-slot I²C, no on-board pull-ups, 0x77 reserved
- [emfcamp/badge-2024-hardware `hexpansion/`](https://github.com/emfcamp/badge-2024-hardware/tree/main/hexpansion) — the official KiCad template + edge-connector footprint this board was derived from; mechanical source of truth

![Top-side render](codemyriad-protogon-qwiic-preview.png)

## Hard constraints — don't trade these away

- **1.0 mm FR4, ENIG finish.** The board edge is the connector (gold card-edge fingers). 1.6 mm or HASL won't seat/contact.
- **Black soldermask, white silk.** Aesthetic choice — some boards go out bare, so a bare board should look finished.
- **The SMD block is optional.** `U1` (CAT24C512 EEPROM), `R1`/`R2` (I²C pull-ups), `C1` (decoupling), `J3` (Qwiic) are the only SMD parts and must be one cleanly-grouped, omittable block. A bare board (none fitted) must be a complete, usable, good-looking protoboard. Pull-ups belong with the EEPROM, not on the base board.
- **The Code Myriad logo stays** (it's fine if hidden once seated).
- **Fits a real 2024 badge** — tab seats, ear clears a neighbour, cable exits outward.

| Item | Value |
|---|---|
| Layers | 2 |
| Thickness | 1.0 mm (required by the hexpansion standard) |
| Material | FR4 |
| Copper | 1 oz |
| Finish | ENIG (required: edge fingers are the contact surface) |
| Soldermask | black |
| Silkscreen | white |
| Edge bevel | none (not a considered choice — your call) |
| Profile | route as drawn: the left connector "mouth" slot **and** the right "ear" are intentional; the fab must not close or "fix" them |
| Size | ~56 × 37 mm (hex body ~48 × 37 mm + edge tongue + ~6 mm ear) |

## Current state — verified, not assumed

- Outline copied from EMF's official template; routing and the EEPROM block placed by an LLM.
- **PCB is the source of truth.** Schematic is stale — it still carries the upstream template's LED, jumper and third resistor, and is missing the new I²C parts. Do **not** run "update PCB from schematic" before reconciling.
- DRC is "clean" only because `.kicad_pro` has most minimums zeroed; under a realistic fab profile it isn't. Re-run against your fab's real capability.
- The I²C bus is routed (12 vias, 0 unconnected in the ratsnest) but copper continuity through the layer changes is unverified, and vias landing inside proto holes is a real risk to check.
- **The EEPROM block (`U1`/`R1`/`R2`/`C1`) sits in the centre of the proto grid**, eating holes and silk. This is the main layout problem to fix.
- Never test-fitted on real hardware. The +6 mm "ear" for `J3` is the only mechanical delta from the proven base outline; whether it clears a populated neighbour is unverified.
- The EEPROM/firmware premise *is* verified against `badge-2024-software`: a CAT24C512 at `0x50` gets full 16-bit addressing and works through the identify/install path. See [DERISK-FINDINGS.md](DERISK-FINDINGS.md).

The detailed (AI-written) review with coordinates and suggested fixes is in [REVIEW-HANDOFF.md](REVIEW-HANDOFF.md). Treat its suggestions as one non-expert opinion, not instructions; where it disagrees with the board file, trust the file.

## Scope

**Must-have**

- [ ] Move the EEPROM block out of the proto grid so the bare board is a clean, full grid and the populated block looks deliberate. Placement is your call.
- [ ] Make the I²C bus genuinely connect in copper to every pad; pass DRC under the real fab profile (not the zeroed rules).
- [ ] Reconcile schematic and PCB — either ERC-clean, or formally make the PCB the source of truth and hand-maintain the parts list. Record the decision.
- [ ] Confirm fit on a real 2024 badge (see fit check below). Watch height: a vertical Qwiic socket is ~8 mm vs a ~7 mm height-restricted interior zone — that's why `J3` sits on the ear.
- [ ] Keep it cheap for a small giveaway run. If machine assembly isn't worth it at low volume (`J3` may need a fixture; `U1`/`J3` are JLCPCB Extended), say so and recommend an alternative.

**Your judgement — I have none here**

- [ ] Pull-ups are 10 k (an LLM typed it). Size them for the real bus capacitance at 400 kHz, or tell me 10 k is right and why.
- [ ] `WP` is tied to GND (always writable, which the badge needs to provision). A solder-jumper to protect the ID block afterwards is cheap if you think it's worth it.
- [ ] Profile, ear, silk, mounting holes, panelisation for the odd outline, edge-finger lead-in, fiducials, test points, revision marker — anything a turnkey assembler will want.

If you think the approach itself is wrong (no ear, no on-board EEPROM, four layers, …), say so. That's the point of hiring you.

## Deliverables

Order-ready package, one design giving both a bare and a populated build:

- updated KiCad project (PCB, schematic, project file) with the rework done
- gerbers (explicit layer list, not saved plot params), drill + map, STEP
- a short fab/order spec flagging the profile is to be routed exactly as drawn (mouth + ear intentional)
- BOM + placement for the populated build with real MPNs (the [current BOM](codemyriad-protogon-qwiic-bom.csv) is a starting point — trust it over a schematic-generated one), plus the bare (omitted) variant
- fresh DRC report under the real ruleset, and an ERC-clean schematic (or a note that the PCB is source of truth)
- the fit-check result (pass/fail, ideally a photo on a real badge)

Done:

- [ ] DRC clean (0 errors, 0 unconnected) under the fab's real rules; copper continuity actually checked, not just the ratsnest
- [ ] bus reaches every pad; EEPROM `0x50` + WP-GND real in copper
- [ ] fits a real 2024 badge (tab seats, ear clears a neighbour, cable exits outward)
- [ ] schematic ↔ PCB reconciled, decision recorded
- [ ] fresh fab outputs, timestamped after the final board save, in both variants

## Fit check

The on-screen envelope check is inconclusive — the decisive test is physical. Print [`../official-hexpansion-paper-template.svg`](../official-hexpansion-paper-template.svg) (or [the upstream original](https://raw.githubusercontent.com/emfcamp/badge-2024-hardware/main/hexpansion/hexpansion_paper_template.svg)) at **1:1**, register the board on the edge connector, and confirm:

1. the hex body sits within the maroon **"template"** outline → validates the base design;
2. the 6 mm ear stays within the light-blue **"hextended"** max envelope and clears a neighbour slot on a populated badge → validates the qwiic delta.

<p align="center">
  <img src="../official-hexpansion-paper-template.svg" width="320" alt="Official 1:1 hexpansion paper fit template (EMF badge-2024-hardware)">
  <br><sub>Official 1:1 paper fit template — <a href="https://github.com/emfcamp/badge-2024-hardware/tree/main/hexpansion">emfcamp/badge-2024-hardware</a> (CERN-OHL-P-2.0). Print at 100%.</sub>
</p>

## Files in this folder

| File | Notes |
|---|---|
| `codemyriad-protogon-qwiic.kicad_pcb` | the board — **source of truth**. Footprints embedded; opens and DRCs without the libs. |
| `codemyriad-protogon-qwiic.kicad_sch` | schematic — **stale**, reconcile before trusting. |
| `codemyriad-protogon-qwiic.kicad_pro` | project + design rules. Minimums mostly zeroed; replace with the fab's profile. |
| `codemyriad-protogon-qwiic-bom.csv` | hand-authored parts list with MPN + LCSC. Trust over a schematic-generated BOM. (Trap noted: an earlier "ZD24C64A-XGMT" alternate is TSSOP, not SOIC — don't order it.) |
| `codemyriad-protogon-qwiic-preview.png`, `-routing.png` | top render + copper x-ray. |
| `BACKGROUND.md` | Tildagon primer + primary sources. Read if hexpansions are new to you. |
| `REVIEW-HANDOFF.md`, `DERISK-FINDINGS.md` | detailed (AI-written) review + de-risking notes. Depth, with caveats. |

Footprint libraries (`*.pretty`) live one folder up at the repo root — harmless lib warnings; footprints are embedded. The base (non-Qwiic) protoboard this derives from is also one folder up, with its fab package in `../fabrication/` (gerbers + drill only, no assembly files) — a reasonable folder-structure template to hand back.
