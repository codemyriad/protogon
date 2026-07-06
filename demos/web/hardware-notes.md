# notes from real-hardware bring-up (for the web badge)

On 2026-07-06 I flashed the starfield demo onto a freshly soldered protogon,
using a real 2024 Tildagon over USB. Almost nothing worked on the first try,
and every failure taught us something the web version should either emulate,
document, or warn about. Facts below are verified on hardware unless marked
otherwise. (Most of the debugging and this write-up were done with Claude;
I drove and checked the results on the bench.)

## the one warning that matters: firmware < v1.12.0 bricks the session

Tildagon OS before v1.12.0 cannot read our EEPROM. Worse than "cannot read":
the old `read_hexpansion_header` sets the read pointer with a plain
address-write followed by STOP, and the Zetta ZD24C64A treats that as the
start of a write cycle. The chip then NACKs everything (the whole slot bus
scans empty) until its power is cut. So on old firmware, merely *inserting*
a protogon wedges it. Reseating "fixes" it, which makes the whole thing look
like a bad solder joint. I chased phantom soldering problems for a good hour.

Upstream fixed exactly this in
[PR #267](https://github.com/emfcamp/badge-2024-software/pull/267)
(commit `e819029`, "Use i2c readfrom_mem family of APIs"): reads now use a
repeated START, which is what the Zetta datasheet requires. First release
with the fix is v1.12.0 (2026-04-30). My badge was on v1.10.0 and showed the
full symptom; after an OTA to v1.12.3 the same board mounts instantly.

For the web version this means:

* If we show setup instructions or a compatibility note anywhere, say it
  plainly: **protogon needs badge firmware v1.12.0 or newer**. On older
  firmware the board will look dead (and will stay dead until reinserted).
* The right way to check the version is `ota.get_version()` (returns e.g.
  `v1.10.0`). Do NOT use `os.uname()`: its `version` field is the MicroPython
  fork's git hash (mine said `5114f2c-dirty`, which exists in no
  badge-2024-software branch; that cost us a detour).
* The symptom to describe for troubleshooting: header read fails, then
  `I2C(n).scan()` returns `[]` for everything in that slot until the board is
  reseated. That exact signature = old firmware, not bad soldering.

Related older bug, already worked around in our tooling:
[issue #59](https://github.com/emfcamp/badge-2024-software/issues/59)
(chunked header writes sent 1-byte addresses to a 2-byte chip; fixed in
v1.8.0, and our flashers write the header in a single 34-byte transaction
anyway).

## what a faithful hexpansion emulation looks like

Verified geometry, in case the web badge ever emulates the EEPROM/filesystem
layer instead of stubbing it:

* Header: 32 bytes at offset 0. Struct `<4s4sHHIHHH9s` (magic `THEX`,
  manifest `"2024"`, fs_offset, page size, total size, vid, pid, unique id,
  friendly name), plus 1 checksum byte: XOR of bytes 1..30 seeded with 0x55.
  v1.12.3 also accepts manifest `"2026"`.
* Our header, as flashed and read back:
  `54484558323032342000200000200000feca62700000537461726669656c6454`
  (fs_offset=32, page=32, size=8192, vid=0xCAFE, pid=0x7062, "Starfield").
  pid 0x7061 is the logo app from the eeprom-image branch; 0x7062 is
  starfield. vid 0xCAFE is the community "open to everyone" vendor id.
* Filesystem: littlefs2 starting at byte 32. Block size is 512 for chips
  >= 8 KiB (64 below that), partition length = total − fs_offset, so our
  8 KiB chip gives 15 blocks and `statvfs` reports 6656 bytes free after
  format. The OS mounts it at `/hexpansion_<slot>` and runs `app.py`.
* Slot detection: the badge keys on address 0x50 being present in the scan
  (`detect_eeprom_addr` in `system/hexpansion/util.py`).

## bus behaviour I did not expect (mostly harmless, worth knowing)

* All six slots (plus front board and system bus) are ONE physical I2C on
  the ESP32-S3 (GPIO 45/46) behind a TCA9548A mux at 0x77. `I2C(n)` selects
  a mux channel. Frequency is fixed at 133 kHz; there is no `freq=` kwarg.
* Scans on a real slot can show ghost devices. My board consistently scanned
  as `[0x2A, 0x40, 0x50, 0x58]` even though the protogon carries only the
  EEPROM at 0x50, and the ghosts moved with the board across slots. Reads at
  0x50 worked fine throughout. I don't have an explanation (address aliasing
  in the chip is my best guess); the practical lesson is that neither the
  sim nor any app code should assume a scan returns exactly the populated
  addresses. The firmware's own detect logic survives this because it only
  asks "is 0x50 there".
* The hexpansion detect line doubles as the slot power gate (it goes to an
  AW9523B expander; board pulls it low = present AND powered). Driving that
  ePin high as an output powers the slot off. That is how we un-wedged the
  chip from software, and it would be the natural hook if the web sim ever
  wants an "eject / reinsert" interaction with true power-cycle semantics.

## the size budget is real

The playground's educational comments do not fit on the chip. Starfield is
6621 bytes as published in the playground; after stripping comments it is
4309 bytes, against 6656 free. So roughly: an EEPROM app has ~6.5 KB for
everything, and our commented style spends about a third of the file on
prose. If the web version ever grows a "flash this to a protogon" story, it
needs the comment-stripping pass (or at least a live byte counter next to
the code). The stripper we used is `slim()` in the eeprom-image branch's
`flash_logo.py`; mind that it skips files containing triple-quoted strings,
so it silently does nothing if a docstring sneaks in (bit me: one docstring
in starfield kept it at 6621 bytes until I removed it).

## tooling that came out of this

* `demos/starfield/flash_raw.py`: flashes and full-tests a protogon from any
  badge, old firmware included. It avoids every frozen firmware helper (raw
  `readfrom_mem` + page writes only), power-cycles the slot first, writes
  and verifies every one of the 8192 bytes with two patterns, then lays down
  header + littlefs + app. Output is a plain PASS/FAIL, so it doubles as the
  test-bench script for the production run.
* `mpremote` quirks we hit, so nobody re-hits them: `mpremote exec/run`
  soft-resets and interrupts the badge OS at an arbitrary boot point, which
  can leave slot power in either state (our script power-cycles to make that
  deterministic). And to inspect what the OS did on its own (mounts etc.),
  connect with `mpremote resume`, otherwise you reset away the very state
  you wanted to look at.

Open question I'd still like an answer to: what are the ghost addresses,
really? If someone gets a logic analyzer on SDA during a scan I'd love to
see it.
