# Protogon

The protogon is a prototyping board for the EMF Tildagon and Spaceagon badges.
If you don't understand what this means, it probably means that this project is not useful to you. But feel free to go down the rabbit hole!

![Protogon, top side](renders/perspective.png)

It can be used to prototype a hexpansion. It features EEPROM (with write-protect jumper) and Qwiic connections.

The idea is based on JakeW's [protoboard hexpansion](https://www.tindie.com/products/jakew/protoboard-hexpansion/).

The board fits a 64 kbit EEPROM. There's a jumper you can short to write protect the EEPROM.
A connector is available to plug in Qwiic/STEMMA QT compatible sensors.

Even when not populated with components the board can be used for a basic hexpansion. The EEPROM is quite a valuable bit to mount, since the badge can recognize the hexpansion and load its code.

## Using files in the repo

The KiCad files are in the root: `codemyriad-protogon.kicad_*`.
The `fabrication/codemyriad-protogon-fab.zip` file is ready to upload to produce the board through a PCB manufacturing service. Make sure you select 1.0 mm FR4 and ENIG finish!
`fabrication/bom-lcsc.csv` contains a Bill Of Materials with LCSC codes.


## Credits

* Many thanks to **JakeW** for the [Protoboard Hexpansion](https://www.tindie.com/products/jakew/protoboard-hexpansion/). The idea for this board came from seeing his one.
* **EMF Camp** for the badge, the hexpansion spec, and the [KiCad template](https://github.com/emfcamp/badge-2024-hardware). This work is based on those KiCad files.
