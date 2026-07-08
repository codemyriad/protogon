# A prototyping board to build your hexpansion

![The protogon board](top.png)

Features:

* 64 Kbit (8 KiB) EEPROM
* EEPROM write protection jumper (P1): short it to write-protect
* Qwiic connector
* I2C pull-ups
* Power LED
* max 3V3 current: 600 mA

## Parts to solder

* `R1`: one 402 Ω resistor
* `R2`, `R3` and `R4`: three 4.7 kΩ resistors
* `C1`: a 0.1 µF capacitor
* `D1`: an LED
* `U1`: a 64 Kbit EEPROM
* `U2`: a Qwiic connector

We missed a mark on the board. This is the correct LED polarity:

![Close-up of D1: the bar of the diode symbol marks the cathode, on the GND side](diode-mark.png)

## Online code editor for badge apps

We extended (vibe coded) the [badge emulator](https://emulator.badge.emfcamp.org/) and added a code editor.
[You can try live coding your badge app here](https://protogon.codemyriad.io/editor)

## Github repository

See https://github.com/codemyriad/protogon for source KiCad files and more
