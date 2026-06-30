# Protogon

> Built with a lot of help from AI agents. The board engineering was finalized and checked by a human; the rest we've proofread and double-checked as much as we could. We think it's genuinely useful, even if some of the writing still reads a little AI. Flagging that up front so you know what you're looking at.

A protoboard hexpansion for the [EMF 2026 badge](https://blog.emfcamp.org/2026/05/28/tildagon-2026-spaceagon/), and a freebie: we're making a pile of these to give away at the camp. It plugs into one of the six slots around the badge edge, gives you a grid of solderable holes to build on, and (this is the new part) carries an I²C EEPROM and a [Qwiic](https://www.sparkfun.com/qwiic) connector, so the hexpansion you build can identify itself to the badge and read a sensor without you ever designing a board.

![Protogon, top side](renders/perspective.png)

## What it is

A "hexpansion" is the EMF badge's expansion format: a small hexagon-shaped board (or just a 1 mm card) that slots into the badge edge. Each slot gives you 3V3, GND, an I²C bus and some GPIO over a 20-pad card-edge connector. The full story is in the official [create-a-hexpansion guide](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/).

Protogon is the boring-but-useful one: a bare passive protoboard. No assembly, nothing to go wrong electrically, cheap enough to hand out by the hundred. What you get:

* a **10×14 grid of plated holes** on 2.54 mm pitch, every hole an exposed ENIG gold ring you can solder to (120 are free; the breakout header sits on the other 20)
* the badge's 20-pad edge connector **broken out to a 2×10 header** (J2), so the I²C bus, the GPIO and the power rails are all reachable from the grid
* power on the silk: top row is `3V3`, bottom row is `GND`
* the detect pin tied to GND, so the badge powers the slot when you insert the board

That much is something you can build anything on. The EEPROM and the Qwiic connector are the two parts a bare protoboard doesn't give you.

## The EEPROM and the Qwiic connector

The badge can read a small I²C EEPROM on a hexpansion to [identify it and auto-install its app](https://tildagon.badge.emfcamp.org/hexpansions/eeprom/). As far as I've seen, most quick hexpansions skip the EEPROM, because getting the address and the write-protect right is fiddly. Protogon already has it: a 24-series EEPROM (U1, a Zetta ZD24C64A, 64 kbit) at address `0x50`, with `WP` pulled low and brought out to the P1 header, so the EEPROM is writable for the badge to provision it.

Right next to it is a [Qwiic / STEMMA QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/what-is-stemma-qt) connector (U2, a side-entry JST-SH). Qwiic is the 4-pin 1 mm I²C connector that a lot of the hobbyist sensor world already speaks, so a cable plugs a sensor straight onto the badge's I²C bus with no soldering. The board supplies the SDA/SCL pull-ups (4.7 kΩ) that the bus needs and the badge deliberately does not.

Put together: if you want a hexpansion that reads a Qwiic sensor and shows up by name on the badge, you plug a sensor into Protogon, flash the EEPROM, write a few lines of MicroPython, and you're done. You never open a PCB tool.

(The grid stays a clean, full grid whether or not the I²C block is fitted. Some of these go out bare. If you order your own, populate the block or leave it off.)

## Renders

Black soldermask, ENIG gold, 1 mm FR4. These are KiCad's own raytraced renders of the real board, not a mockup.

| Top | Bottom |
| --- | --- |
| ![top](renders/top.png) | ![bottom](renders/bottom.png) |

## Building or ordering your own

It's open hardware ([CERN-OHL-P-2.0](LICENSE)), the whole design is in this repo, and you're welcome to make it. Two things will bite you if you don't know the badge:

* **1.0 mm FR4, ENIG finish, not the fab defaults.** The board edge *is* the connector: the gold fingers on the tongue are what contact the badge. A 1.6 mm card won't fit a 1 mm slot, and HASL's uneven surface won't contact those fingers reliably. Most fabs default to 1.6 mm and HASL, so you have to change both. JLCPCB and PCBWay do 1 mm + ENIG; in the EU, Beta Layout and Multi-CB do 1 mm.
* **Route the outline exactly as drawn.** The slot on the left edge (the connector "mouth" the badge tongue slides into) and the little "ear" the Qwiic connector sits on are both intentional. A fab that helpfully "closes up" the outline will ruin the board.

Fab spec:

| | |
|---|---|
| Layers | 2 |
| Thickness | 1.0 mm |
| Material | FR4, 1 oz copper |
| Finish | ENIG (required) |
| Soldermask | black |
| Silkscreen | white |
| Edge bevel | none |

The order outputs live in [`fabrication/`](fabrication/): Gerbers and drill zipped in [`codemyriad-protogon-fab.zip`](fabrication/codemyriad-protogon-fab.zip), a [STEP model](fabrication/step/), the [DRC report](fabrication/drc-report.txt) (0 errors, 0 unconnected pads), and a [parts list](fabrication/bom.csv) with LCSC numbers. The SMD parts are the I²C block (the EEPROM, the Qwiic connector, the pull-ups and a decoupling cap) plus a small power LED and its resistor; everything else is through-hole or just plated holes. We order bare boards and hand-solder the few parts, so the BOM is built for hand assembly, not a pick-and-place line. The [300-board giveaway order](fabrication/BOM_300boards_mouser.csv) is there too if you want the quantities we used.

Making the EEPROM actually identify your hexpansion is a firmware step, not a hardware one: point [`prepare_eeprom.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/scripts/prepare_eeprom.py) at the right I²C port with a real VID/PID, write it once, and the badge picks it up on insert. The detection logic is in [`util.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/system/hexpansion/util.py). I'd smoke-test a read and a write on a real badge before committing to a quantity. It's two minutes and it's the one thing the files can't prove for you.

## Does it fit?

The hexagon body is the proven outline straight from EMF's template, so that part is known good. The one thing I can't fully settle from the files is whether the Qwiic ear clears a neighbour in a fully-populated badge. The check is cheap: print [`official-hexpansion-paper-template.svg`](official-hexpansion-paper-template.svg) at 100%, lay a 1:1 print of the board on it registered on the edge connector, and confirm the body sits inside the "template" outline and the ear stays inside the "hextended" envelope. We do the final seat-and-clearance check on a real badge before ordering a batch.

## How this was made

Honest provenance, because it should count for something on a board you're about to trust with your soldering iron: the first cut was laid out by an LLM, the naive way, and it showed (the Qwiic connector bolted onto an awkward tab, the EEPROM dumped in the middle of the grid eating holes and silk). A human PCB designer then redid the placement, routed the I²C bus properly in copper, sized the pull-ups, brought the write-protect out to a jumper, and got DRC down to no errors and no unconnected pads. The board here is the human's work. The earlier protoboard-only prototype, and the Blender render pipeline we used before switching to KiCad's own renders, are kept in [`archive/`](archive/) rather than deleted.

## What's in here

| Path | What |
|---|---|
| `codemyriad-protogon.kicad_pcb` / `.kicad_sch` / `.kicad_pro` | the KiCad design |
| [`fabrication/`](fabrication/) | Gerbers, drill, STEP, BOM, placement, DRC report |
| [`renders/`](renders/) | the board renders above |
| `*.pretty`, `JLC2KiCad_lib/` | the footprint and symbol libraries the board uses |
| `official-hexpansion-paper-template.svg` | EMF's 1:1 paper fit template |
| [`archive/`](archive/) | the original protoboard-only prototype and the old Blender pipeline |

## Credits

* **JakeW** for the [Protoboard Hexpansion](https://www.tindie.com/products/jakew/protoboard-hexpansion/) ([jakew.me](https://jakew.me)) that the form factor and the proto-field approach are functionally inspired by.
* **EMF Camp** for the badge, the hexpansion spec, and the [KiCad template](https://github.com/emfcamp/badge-2024-hardware) our outline and edge-connector footprint derive from, released under CERN-OHL-P v2.

## More on the badge

* [Tildagon badge docs](https://tildagon.badge.emfcamp.org/) and [creating hexpansions](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/)
* [Badge hardware](https://github.com/emfcamp/badge-2024-hardware) and [badge software](https://github.com/emfcamp/badge-2024-software)
* [2026 Spaceagon announcement](https://blog.emfcamp.org/2026/05/28/tildagon-2026-spaceagon/)
