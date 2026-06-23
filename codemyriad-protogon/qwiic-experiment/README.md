# Protogon Qwiic + EEPROM hexpansion

This is a small PCB I want to manufacture, and I'd like someone who has actually
designed and ordered boards to look at it before I do.

The honest reason: I laid it out with an LLM (Claude Code). Vibe-coded, basically, and
no one with real PCB experience has ever seen it. It passes KiCad's own checks, but I
don't trust that, and I'll explain below why you shouldn't either. Before I spend money
on a batch (some to give away at a hacker camp), I want a human to confirm the board and
the parts will actually work, to fix the parts that won't, and to hand it back ready to
order.

So this is a brief, not a spec. Most of the design decisions in the file are not
decisions, and you should feel free to redo them (see ["what's a real choice and what isn't"](#whats-a-real-choice-and-what-isnt)).

## What it is

It's a [hexpansion](https://tildagon.badge.emfcamp.org/hexpansions/): an add-on board for
the [Tildagon](https://tildagon.badge.emfcamp.org/), the reusable hexagonal badge from
[Electromagnetic Field](https://www.emfcamp.org/) (a UK hacker camp). The badge has six
slots around its edge; a hexpansion plugs into one.

This hexpansion is a protoboard. The base of it is a 10×14 grid of 2.54 mm
through-holes you solder your own parts onto, with the badge's edge-connector signals
broken out to a 2×10 header (J2). On top of that, it adds an optional I²C block so the
badge can [recognise the hexpansion and install its app straight off an on-board
EEPROM](https://tildagon.badge.emfcamp.org/hexpansions/eeprom/):

* `U1`, a CAT24C512 I²C EEPROM (the badge reads a `THEX` header plus a LittleFS image from it)
* `R1`/`R2`, the I²C pull-ups
* `C1`, decoupling
* `J3`, a [Qwiic / STEMMA QT](https://www.sparkfun.com/qwiic) connector (the 1.0 mm 4-pin
  JST-SH that [SparkFun and Adafruit both use](https://learn.adafruit.com/introducing-adafruit-stemma-qt)),
  so you can chain external I²C boards too

![Top-side render of the board](codemyriad-protogon-qwiic-preview.png)

The outline and the edge connector come from EMF's official
[badge-2024-hardware](https://github.com/emfcamp/badge-2024-hardware) hexpansion template
(CERN-OHL-P-2.0). The firmware behaviour I'm relying on (the `0x50` EEPROM scan and the
install path) is in [badge-2024-software](https://github.com/emfcamp/badge-2024-software).

## What's a real choice and what isn't

This is the most important section, so I'll be blunt about it. Almost everything in the
KiCad file was produced by an LLM with no idea what it's doing. Please don't mistake those
artefacts for decisions. Here's the line.

**Decided on purpose. Please keep these.**

* **Cheap.** This is a giveaway board, so cost matters more than anything fancy. Let it
  drive your part choices and the assembly approach.
* **It should look cool.** The black soldermask is a deliberate choice, not a default.
  Some of these go out bare, so a bare board should look like a finished object.
* **The Code Myriad logo stays on it.** It's fine if the logo ends up hidden once the
  hexpansion is seated in the badge (it currently sits near the neck, which inserts). Just
  don't drop it in a redesign.
* **The EEPROM and every SMD part are optional.** The board has to be fully functional and
  good-looking with none of them fitted. More on this [below](#one-hard-requirement-the-smd-parts-are-optional).

And one physical given that isn't a "choice" so much as the whole point: it has to plug
into a real Tildagon and behave as a hexpansion. It must fit a badge slot, mate with the
edge connector, and (when the EEPROM is fitted) let the badge identify it. The outline was
copied from EMF's template to get that for free, but nobody has confirmed it on real
hardware, so even "it fits" is currently unverified.

**Not actually decided. Change anything here if your experience says so.**

* the board profile, and the little rounded "ear" the connector sits on
* the connector itself: that it's Qwiic, that it's that exact JST part, and where it sits
* where the EEPROM and the rest of the SMD block live on the board
* the pull-up values (they're 10 k because an LLM typed 10 k)
* two layers vs more, the exact dimensions, the "no bevel" on the edge fingers, and so on

If any of that is wrong, or there's a cheaper or better way, I'd rather you change it than
preserve it out of politeness. None of it was a considered call.

## Where it actually stands

The outline came out of a Python script driving KiCad; the routing and the EEPROM block
were placed by the LLM. I then had other LLMs review it, and that review is in the two
appendix files below. It's useful, but it's still machine-generated.

So treat every "it's fine" and "verified" in this repo as unconfirmed. A few specific
things I already suspect are wrong (I'm not the expert, so please use your own judgement):

* **The EEPROM placement, which is the one that bothers me most.** `U1`/`R1`/`R2`/`C1`
  sit in the dead centre of the proto grid, eating into the holes and silk.
* **DRC is "clean" against a ruleset with most minimums set to 0.** Run it under a real
  fab profile and it isn't (a review pass under a JLCPCB-ish profile turned up a couple
  dozen violations).
* **The bus is routed (12 vias, KiCad reports 0 unconnected), but that only means the
  ratsnest is happy.** It doesn't prove the copper truly connects through every layer
  change, and nobody has confirmed the vias land sensibly (and not inside a proto hole).
* **The schematic is out of sync with the board.** It's a hybrid: it still carries an
  LED, a jumper and a third resistor from the upstream template that this board never
  places, alongside the new I²C parts. The `.kicad_pcb` is the source of truth; please
  don't "update PCB from schematic" before reconciling the two.
* **It has never been test-fitted in a real 2024 badge.** I added about 6 mm of "ear" for
  the connector, and I don't know if the board still fits the badge slot envelope or
  clears a neighbouring hexpansion.

I might be wrong about some of these. I'd rather you tell me than humour me.

## What I'd like you to do

The short version: validate it, improve the weak parts, and hand it back ready to order. I
don't just want a list of problems (though I'll take that too). I'd like you to make the
KiCad changes and produce files I can send to a fab.

Roughly in the order I care about:

**Must-have**

- [ ] Get the EEPROM block out of the middle of the proto grid, so the bare board is a
  full, clean grid again and the populated block looks deliberate. Where it goes and how
  is your call.
- [ ] Make the I²C bus genuinely connect in copper to every pad, and pass DRC under the
  real capability profile of whatever fab we use, not the zeroed rules it ships with.
- [ ] Reconcile the schematic with the board and get ERC clean (or formally make the PCB
  the source of truth and hand-maintain the parts list). Your call which.
- [ ] Confirm it fits. There's a [1:1 paper template](../official-hexpansion-paper-template.svg)
  in the repo; the real test is registering it (or the board) on a real badge and checking
  the body and the connector ear against the slot and a neighbour. This is the gate I can't
  close from a screen.
- [ ] Keep it cheap. Prefer parts and a process that suit a small giveaway run. If
  machine-assembling these particular parts isn't worth it at low volume (the connector may
  need an assembly fixture, and a couple of parts aren't in the cheap basic library), tell
  me, and tell me what you'd do instead.

**Your judgement (I have none here)**

- [ ] The pull-ups are 10 k. For I²C rise time that looks weak to me, especially once a
  cable and a downstream board hang off the connector. Size them properly, or tell me 10 k
  is right and why.
- [ ] The EEPROM's write-protect pin is tied to ground (always writable), which the badge
  needs to provision it. If you think the identity should be protectable afterwards, a
  solder-jumper is cheap.
- [ ] The board profile, the connector ear, and the silk. Since these get given away bare,
  I want the bare board to look intentional, not like a base board with a lump bolted on.
- [ ] The mounting-hole footprint, panelisation for the odd outline, the edge-connector
  lead-in, and anything a turnkey assembler will want (fiducials, test points, a revision
  marker). I haven't thought about most of these.

The two appendix files go through all of this in detail, with coordinates, and they even
suggest specific fixes. Treat those suggestions as one (non-expert) opinion to weigh, not
as instructions. You're the one who's done this for real.

## One hard requirement: the SMD parts are optional

We're going to hand out some boards bare (no SMD parts at all) and assemble others with the
EEPROM block fitted. Same PCB, two builds. So:

* The EEPROM, the two pull-ups, the decoupling cap and the Qwiic connector (`U1`, `R1`,
  `R2`, `C1`, `J3`) are the only SMD parts, and they should be one cleanly-grouped,
  optional block.
* A bare board (none of those fitted) has to be a complete, usable, good-looking
  protoboard on its own. That's exactly why the EEPROM sitting in the middle of the grid is
  a real problem and not a cosmetic one.
* The pull-ups belong with the EEPROM, not on the base board, so a bare board doesn't have
  stray pull-ups going nowhere.
* How I'd expect this to be orderable: one set of gerbers and drill, and two parts +
  placement sets, where "bare" just omits the SMD lines. If you'd do it differently, say so.

Everything else (the edge-connector fingers, the 2×10 header, the mounting holes, the
proto grid) is through-hole or mechanical and gets hand-soldered or left to the user. None
of it should land on a pick-and-place file.

## What I'd want back

A finalised design plus a package I can order from directly, built so the same files give
both the bare board and the populated one:

* the updated KiCad project (PCB, schematic, project file), with the rework done
* gerbers (plotted from an explicit layer list, not the saved plot params), drill files
  and map, and a STEP model
* a short fab / order spec (the table below), flagging that the profile is to be routed
  exactly as drawn: both the connector "mouth" slot on the left and the ear on the right
  are intentional, and the fab must not close or "fix" them
* a parts list and a placement file for the populated build, with real part numbers (the
  [current parts list](codemyriad-protogon-qwiic-bom.csv) is a starting point), plus the
  omitted version for the bare build
* a fresh DRC report under the real ruleset, and an ERC-clean schematic (or a note that the
  PCB is the source of truth)
* the fit-check result (pass/fail, ideally a photo on a real badge)

and, at the end, two order packages from one design: one bare, one populated.

Done, the way I'd phrase it:

- [ ] DRC clean (0 errors, 0 unconnected) under the actual fab's rules, with copper
  continuity actually checked, not just the ratsnest
- [ ] the bus reaches every pad; the EEPROM address and write-enable are real in copper
- [ ] fits a real 2024 badge (tab seats, ear clears a neighbour, cable exits outward)
- [ ] schematic and PCB reconciled, decision recorded
- [ ] fresh fab outputs, timestamped after the final board save, in both variants

## Fab spec

These are the current settings. The black soldermask is a real choice; "cheap" is what
drives the rest, so revisit anything here if there's a cheaper or better call.

| Item | Value |
|---|---|
| Layers | 2 |
| Thickness | 1.0 mm |
| Material | FR4 |
| Copper | 1 oz |
| Finish | ENIG |
| Soldermask | **black** |
| Silkscreen | white |
| Edge bevel | none (not a considered choice) |
| Profile | route as drawn (left connector mouth + right ear are intentional) |
| Size | about 56 × 37 mm overall (hex body ~48 × 37 mm, plus the edge tongue and a ~6 mm ear) |

## What's in this folder

* `codemyriad-protogon-qwiic.kicad_pcb`: the board, and the source of truth. Footprints
  are embedded, so it opens and runs DRC without the libraries.
* `codemyriad-protogon-qwiic.kicad_sch`: the schematic. Out of sync with the board (see
  above); reconcile before trusting it.
* `codemyriad-protogon-qwiic.kicad_pro`: project and design rules. The rules are mostly
  zeroed; replace them with the target fab's profile.
* `codemyriad-protogon-qwiic-bom.csv`: hand-written parts list with manufacturer and LCSC
  numbers. Trust this over a schematic-generated one. (It already notes one trap: an
  earlier "ZD24C64A-XGMT" alternate is the wrong package, TSSOP not SOIC. Don't order it.)
* `codemyriad-protogon-qwiic-preview.png`, `codemyriad-protogon-qwiic-routing.png`: the
  render above, and an x-ray of the copper.
* `REVIEW-HANDOFF.md` and `DERISK-FINDINGS.md`: the detailed (AI-written) review and
  de-risking notes: the firmware EEPROM path, the parts, the fit question, and a long DFM
  checklist with coordinates. Read them for depth, with two caveats. They were written at
  different points during the build, so where they disagree with the board file in front of
  you, trust the file (for instance, `REVIEW-HANDOFF` calls the bus "unrouted", and it has
  since been routed). And they're as machine-generated as the board itself.

The footprint libraries (`*.pretty`) live one folder up, at the repo root, which is why
KiCad shows a couple of harmless library warnings. The plain (non-Qwiic) protoboard this is
based on is also one folder up, with its fabrication package in `../fabrication/` (gerbers
and drill only, no assembly files yet). That's a reasonable template for the folder
structure to hand back.

## Last thing

If you look at this and think the approach itself is wrong (the connector shouldn't be on
an ear, the EEPROM shouldn't be on this board at all, it should be four layers, whatever),
I want to hear that. The whole point of bringing in someone who's done this for real is to
catch the things I can't see. Tell me where I'm wrong.
