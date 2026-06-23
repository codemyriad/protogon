# Tildagon hexpansion primer (for the PCB reviewer)

You know PCBs; you've probably never seen a Tildagon. This is the minimum to work on
[the board](README.md), plus the primary sources. The official spec is spread across a few
pages, so the load-bearing facts are collected here. Where the docs and the team's own chat
disagree, the resolved answer is given.

## 30-second orientation

* [Electromagnetic Field (EMF)](https://www.emfcamp.org/) is a UK hacker camp.
* The [Tildagon](https://tildagon.badge.emfcamp.org/) is its reusable badge (ESP32-S3, round
  screen, six slots around the edge).
* A [hexpansion](https://tildagon.badge.emfcamp.org/hexpansions/) is a hexagon-shaped board
  (or just 1 mm card) that plugs into one slot. The badge can read an optional I²C EEPROM on
  it to [identify the hexpansion and auto-install its app](https://tildagon.badge.emfcamp.org/hexpansions/eeprom/).
* This board is a protoboard hexpansion that also carries that optional EEPROM and a Qwiic
  connector.

## Mechanical (hard constraints)

* **1.0 mm thick.** Not the 1.6 mm / 0.8 mm fab defaults. Strictly, only the in-slot region
  (everything below the "fit in slot" line on the template) must be 1.0 mm; ordering the
  whole board at 1.0 mm is the simple, safe path.
* **ENIG finish, never HASL.** The board edge *is* the connector (card-edge / SFP-style gold
  fingers, no connector part). HASL is uneven and the fingers won't contact reliably.
* **Outline:** regular hexagon, 32 mm across flats (~36.65 mm point to point). The plug-in
  tab protrudes ~17.75 mm and is ~9.2 mm × 6.5 mm. These prose numbers are summaries: the
  exact finger pitch/width/length lives only in the KiCad template footprint, so take finger
  geometry from there, not from this page.
* **"Hextended" envelope.** You may extend past the hexagon, but the overhang must stay
  within the continuation of the hexagon's edge lines, or it collides with a neighbouring
  slot. The paper template draws this max envelope explicitly.
* **Height-restricted zone (~7 mm).** Tall parts must clear it. A vertical Qwiic / STEMMA QT
  socket is ~8 mm tall, so it has to sit at the outer edge or on a hextended tab, not in the
  interior. The exact zone is template-only; read it off the KiCad / SVG. (This is the single
  biggest fit risk for a board with a Qwiic connector.)
* **Mounting holes:** two optional M2, 25 mm apart. The connector's friction retains the
  board; the holes are a stiffness / alignment aid, not structural.
* **Copper-to-edge:** the template ships at 0.01 mm, which trips fab DRC. Pull copper back to
  0.25 mm from the outline before plotting. This does not apply to the edge fingers, which
  must reach the edge.

## Edge connector (20 gold pads, card-edge)

Two rows of ten. Bottom row pins 1-10, top row pins 11-20.

| Pin | Signal | Pin | Signal |
|----:|--------|----:|--------|
| 1 | GND | 11 | GND |
| 2 | LowSpeed 1 | 12 | HighSpeed 1 |
| 3 | LowSpeed 2 | 13 | HighSpeed 2 |
| 4 | **I²C SDA** | 14 | GND |
| 5 | **I²C SCL** | 15 | **+3V3** |
| 6 | **Detect** | 16 | **+3V3** |
| 7 | LowSpeed 3 | 17 | GND |
| 8 | LowSpeed 4 | 18 | HighSpeed 3 |
| 9 | LowSpeed 5 | 19 | HighSpeed 4 |
| 10 | GND | 20 | GND |

* **3.3 V only**, up to **600 mA** per slot (pins 15/16). That is your Qwiic VCC; there is no
  higher rail.
* **Detect (pin 6) ties to GND** on the hexpansion. It signals presence and gates slot power;
  leave it floating and the slot can stay unpowered. (This board hard-ties it, correctly.)
* HighSpeed = direct ESP32-S3 GPIO; LowSpeed = via a badge-side GPIO expander. Not used by
  this board, but that's what those pads are.

Authoritative pinout + mechanical rules: the
[create-a-hexpansion guide](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/)
and the [badge-hardware reference](https://tildagon.badge.emfcamp.org/tildagon-apps/reference/badge-hardware/).

## I²C and the identify EEPROM

* **Each of the six slots is its own isolated I²C bus** (no shared mux across slots). Address
  collisions only matter within your own card.
* **No pull-ups on the badge side.** The hexpansion must provide the SDA/SCL pull-ups (this
  board: R1/R2). The EEPROM and any Qwiic chain share them.
* **0x77 is reserved** by the badge. The badge probes **0x50 and 0x57** for the identify
  EEPROM, so keep any other I²C device out of the whole `0x50`-`0x57` block.
* **The identify EEPROM is optional.** When present, the badge reads a 32-byte `THEX` header,
  then a LittleFS image holding `app.py`, and auto-installs it. **WP must be tied to GND** so
  the badge can write it. A CAT24C512 at `0x50` gets full 16-bit addressing and is the largest
  cleanly-supported single chip. Community designs often strap `0x57` instead; `0x50` is fine
  for this part.
* **Provisioning is firmware-side, not a board change:** in
  [`prepare_eeprom.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/scripts/prepare_eeprom.py)
  switch the default header from `M24C16` to `CAT24C512`, set the slot's I²C port, and set a
  real VID/PID (the templates ship a placeholder). The detection logic is in
  [`util.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/system/hexpansion/util.py).

## The Qwiic / STEMMA QT connector

* 4-pin **JST-SH, 1.0 mm pitch**. Fixed order: **1 = GND, 2 = 3V3, 3 = SDA, 4 = SCL**. One
  footprint serves both [Qwiic](https://www.sparkfun.com/qwiic) and
  [STEMMA QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/what-is-stemma-qt)
  (they are cross-compatible). 3.3 V only, so no level shifting.

## Gotchas the badge team actually hit (from their chat)

* The official template is now **KiCad 10**; older KiCad can't open it. In the template,
  **tracks and vias are hidden by default** (toggle them in the Objects tab) and it **fails
  ERC by default** (via sizes set wrong when it was authored). Both are template artefacts,
  not your mistakes.
* **1 mm + ENIG is the single most common fab mistake**, because every fab defaults to
  1.6 mm + HASL. Change both.
* **Few fabs offer 1 mm + ENIG.** JLCPCB and PCBWay (China) do; in the EU, Beta Layout and
  Multi-CB do 1 mm, Aisler does not obviously. Check before committing.
* For a small giveaway run, fab part markup plus assembly setup often costs more than buying
  the parts (Mouser / LCSC) and hand-soldering. Panelising one design and self-depaneling is
  the cheap path.

## Primary sources

Spec and mechanical:
* [Create a hexpansion](https://tildagon.badge.emfcamp.org/hexpansions/creating-hexpansions/) (pinout, 1 mm, ENIG, 32 mm flats, 600 mA, no I²C pull-ups, 0x77 reserved)
* [Hexpansions hub](https://tildagon.badge.emfcamp.org/hexpansions/)
* [Official KiCad template + edge-connector footprint](https://github.com/emfcamp/badge-2024-hardware/tree/main/hexpansion) (mechanical source of truth; clone the whole repo)
* [1:1 paper fit template (SVG)](https://raw.githubusercontent.com/emfcamp/badge-2024-hardware/main/hexpansion/hexpansion_paper_template.svg) (print at 100%, lay the board on it)

Electrical and firmware:
* [Badge hardware reference](https://tildagon.badge.emfcamp.org/tildagon-apps/reference/badge-hardware/) (per-slot I²C, GPIO map, ADC only on slots 4-6)
* [EEPROM identify guide](https://tildagon.badge.emfcamp.org/hexpansions/eeprom/) (32-byte `THEX` header, checksum, LittleFS)
* [`util.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/system/hexpansion/util.py) and [`prepare_eeprom.py`](https://github.com/emfcamp/badge-2024-software/blob/main/modules/scripts/prepare_eeprom.py) (detection + provisioning)
* [hexpansion-firmwares](https://github.com/emfcamp/hexpansion-firmwares) (register a VID/PID via a GitHub issue)

Connectors and a worked example:
* [SparkFun Qwiic](https://www.sparkfun.com/qwiic) · [Adafruit STEMMA QT](https://learn.adafruit.com/introducing-adafruit-stemma-qt/what-is-stemma-qt)
* [A real EEPROM hexpansion in KiCad](https://github.com/MatthewWilkes/uk-map-hexpansion) (Matthew Wilkes, EMF badge software lead)

The detailed, board-specific review notes are in [REVIEW-HANDOFF.md](REVIEW-HANDOFF.md) and
[DERISK-FINDINGS.md](DERISK-FINDINGS.md). The job itself is in [README.md](README.md).
