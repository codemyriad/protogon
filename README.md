# Protogon

> Built with a lot of help from AI agents. The board engineering was finalized and checked by a human; the rest we proofread and checked as much as we could. Useful, we think, even if some of the writing still reads a little AI.

A protoboard hexpansion for the [EMF 2026 badge](https://blog.emfcamp.org/2026/05/28/tildagon-2026-spaceagon/), free at the camp. It plugs into one of the badge's six edge slots and gives you a grid of solderable holes, plus an I²C EEPROM and a [Qwiic](https://www.sparkfun.com/qwiic) connector so the hexpansion you build can identify itself to the badge and read a sensor without designing a board.

![Protogon, top side](renders/perspective.png)

## What it is

A "hexpansion" is the EMF badge's expansion format: a hexagon-shaped board (or a 1 mm card) that slots into the badge edge. Each slot gives you 3V3, GND, an I²C bus and some GPIO over a 20-pad card-edge connector ([create-a-hexpansion guide](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/)).

Protogon is a bare passive protoboard: no assembly, nothing to go wrong, cheap by the hundred. What you get:

* a **10×14 grid of plated holes** on 2.54 mm pitch, every hole an exposed ENIG gold ring (120 free; the breakout header takes the other 20)
* the badge's 20-pad edge connector **broken out to a 2×10 header** (J2), so the I²C bus, GPIO and power rails are reachable from the grid
* power on the silk: top row `3V3`, bottom row `GND`
* the detect pin tied to GND, so the badge powers the slot on insert

## The EEPROM and the Qwiic connector

The badge reads a small I²C EEPROM to [identify a hexpansion and auto-install its app](https://tildagon.badge.emfcamp.org/hexpansions/eeprom/). Most quick hexpansions skip it (the address and write-protect are fiddly). Protogon has one: a 24-series EEPROM (U1, Zetta ZD24C64A, 64 kbit) at `0x50`, WP pulled low and broken out to the P1 header so the badge can provision it.

Next to it, a [Qwiic / STEMMA QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/what-is-stemma-qt) connector (U2, side-entry JST-SH). Qwiic is the 4-pin 1 mm I²C connector most hobbyist sensors already use, so a cable drops a sensor onto the badge's I²C bus with no soldering. The board carries the SDA/SCL pull-ups (4.7 kΩ); the badge has none.

So for a hexpansion that reads a Qwiic sensor and shows up by name on the badge: plug in the sensor, flash the EEPROM, write a few lines of MicroPython. No PCB tool.

The grid stays full whether or not the I²C block is fitted. Some go out bare; build your own with the block populated or left off.

## Renders

Black soldermask, ENIG gold, 1 mm FR4. KiCad raytraced renders of the real board.

| Top | Bottom |
| --- | --- |
| ![top](renders/top.png) | ![bottom](renders/bottom.png) |

## Building or ordering your own

Open hardware ([CERN-OHL-P-2.0](LICENSE)); the whole design is here. Two things bite you if you don't know the badge:

* **1.0 mm FR4, ENIG, not the fab defaults.** The board edge *is* the connector: the gold fingers on the tongue contact the badge. A 1.6 mm card won't fit a 1 mm slot, and HASL's uneven surface won't contact the fingers reliably. Most fabs default to 1.6 mm and HASL; change both. JLCPCB and PCBWay do 1 mm + ENIG; in the EU, Beta Layout and Multi-CB do 1 mm.
* **Route the outline exactly as drawn.** The left-edge slot (the connector "mouth" the badge tongue slides into) and the "ear" the Qwiic connector sits on are both intentional. A fab that "closes up" the outline will ruin it.

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

Outputs in [`fabrication/`](fabrication/): Gerbers + drill zipped in [`codemyriad-protogon-fab.zip`](fabrication/codemyriad-protogon-fab.zip), a [STEP model](fabrication/step/), the [DRC report](fabrication/drc-report.txt) (0 errors, 0 unconnected), and a [BOM](fabrication/bom.csv) with LCSC numbers. SMD parts are the I²C block (EEPROM, Qwiic, pull-ups, decoupling cap) plus a power LED and its resistor; the rest is through-hole or plated holes. We hand-solder, so the BOM is for hand assembly, not a pick-and-place. The [300-board giveaway order](fabrication/BOM_300boards_mouser.csv) is there too.

Getting the badge to identify your board is firmware, not hardware: point [`prepare_eeprom.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/scripts/prepare_eeprom.py) at the right I²C port with a real VID/PID, write once, and the badge picks it up on insert (detection logic in [`util.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/system/hexpansion/util.py)). Smoke-test a read and write on a real badge before you order a batch; the files can't prove that part.

## How this was made

The first cut was laid out by an LLM, and it showed: the Qwiic connector bolted onto an awkward tab, the EEPROM dumped mid-grid eating holes and silk. A human PCB designer redid the placement, routed the I²C bus in copper, sized the pull-ups, brought WP out to a jumper, and got DRC to zero errors and zero unconnected. That's the board here. The bare-protoboard prototype and the old Blender render pipeline are kept in [`archive/`](archive/).

## What's in here

| Path | What |
|---|---|
| `codemyriad-protogon.kicad_pcb` / `.kicad_sch` / `.kicad_pro` | the KiCad design |
| [`fabrication/`](fabrication/) | Gerbers, drill, STEP, BOM, placement, DRC report |
| [`renders/`](renders/) | the board renders above |
| `*.pretty`, `JLC2KiCad_lib/` | the footprint and symbol libraries |
| `official-hexpansion-paper-template.svg` | EMF's 1:1 paper fit template |
| [`archive/`](archive/) | the original protoboard-only prototype and old Blender pipeline |

## Credits

* **JakeW** for the [Protoboard Hexpansion](https://www.tindie.com/products/jakew/protoboard-hexpansion/) ([jakew.me](https://jakew.me)) that the form factor and proto-field approach are inspired by.
* **EMF Camp** for the badge, the hexpansion spec, and the [KiCad template](https://github.com/emfcamp/badge-2024-hardware) our outline and edge-connector footprint derive from, released under CERN-OHL-P v2.

## More on the badge

* [Tildagon badge docs](https://tildagon.badge.emfcamp.org/) and [creating hexpansions](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/)
* [Badge hardware](https://github.com/emfcamp/badge-2024-hardware) and [badge software](https://github.com/emfcamp/badge-2024-software)
* [2026 Spaceagon announcement](https://blog.emfcamp.org/2026/05/28/tildagon-2026-spaceagon/)
