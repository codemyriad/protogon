# flash_raw.py -- EEPROM full test + starfield flash, raw I2C only.
#
# Deliberately avoids ALL frozen firmware helpers (system.hexpansion.*,
# eeprom_i2c): this badge's firmware build (5114f2c, 2025-11-25) predates the
# v1.12.0 fix (badge-2024-software e819029 / PR #267) and its
# read_hexpansion_header wedges Zetta ZD24C64A EEPROMs with a bare
# address-write + STOP. Everything here uses readfrom_mem (repeated START)
# and plain page writes, both verified safe on this chip.
#
#   mpremote cp app_slim.py :starfield_payload.py + run flash_raw.py

PORT = 5
FRIENDLY = "Starfield"
APP_PAYLOAD = "/starfield_payload.py"
# THEX header, manifest 2024, fs_offset=32, page=32, size=8192,
# vid=0xCAFE pid=0x7062, name "Starfield" -- generated with the current
# (post-fix) firmware's HexpansionHeader format so an updated badge parses it.
HEADER = bytes.fromhex(
    "54484558323032342000200000200000feca62700000537461726669656c6454"
)

import os
import struct
import time
import vfs
from machine import I2C
from egpio import ePin

CHIP = 8192
PAGE = 32
FS_OFFSET = 32
BLOCK = 512
MOUNT = "/protogon_flash"
ND = {1: (2, 12), 2: (2, 13), 3: (1, 8), 4: (1, 9), 5: (1, 10), 6: (1, 11)}
EEPROM_ADDR = 0x50


def die(*lines):
    print()
    print("#" * 60)
    print("#  RESULT: FAIL")
    for ln in lines:
        print("#  " + ln)
    print("#" * 60)
    raise SystemExit


def unmount(path):
    try:
        vfs.umount(path)
    except OSError:
        pass


# power-cycle the slot: guarantees the chip starts in a clean state
_p = ePin(ND[PORT], ePin.OUT)
_p.on()
time.sleep_ms(400)
_p.off()
time.sleep_ms(400)

i2c = I2C(PORT)


def wait_ready():
    # after a page write the chip NACKs until its internal cycle ends;
    # poll with a 1-byte current-address read (verified safe on this part)
    for _ in range(500):
        try:
            i2c.readfrom(EEPROM_ADDR, 1)
            return True
        except OSError:
            time.sleep_ms(1)
    return False


def write_page(memaddr, chunk):
    try:
        i2c.writeto(EEPROM_ADDR, struct.pack(">H", memaddr) + chunk)
    except OSError:
        die("EEPROM NACKed a write at 0x%04X." % memaddr,
            "Check the 0x50 solder joints and that P1 is OPEN (P1 shorted =",
            "write-protected).")
    if not wait_ready():
        die("EEPROM never finished a write at 0x%04X." % memaddr,
            "Most likely write-protected: OPEN the P1 jumper and rerun.")


def write_region(start, data):
    off = 0
    while off < len(data):
        memaddr = start + off
        room = PAGE - (memaddr % PAGE)
        n = room if (len(data) - off) > room else (len(data) - off)
        write_page(memaddr, data[off:off + n])
        off += n


def read_region(start, n):
    return i2c.readfrom_mem(EEPROM_ADDR, start, n, addrsize=16)


class RawPartition:
    # same geometry the post-fix firmware uses to mount hexpansions:
    # fs at byte 32, 512-byte blocks, (8192-32)//512 = 15 blocks
    def readblocks(self, n, buf, off=0):
        a = FS_OFFSET + n * BLOCK + off
        buf[:] = read_region(a, len(buf))

    def writeblocks(self, n, buf, off=0):
        write_region(FS_OFFSET + n * BLOCK + off, bytes(buf))

    def ioctl(self, op, arg):
        if op == 3:
            return
        if op == 4:
            return (CHIP - FS_OFFSET) // BLOCK
        if op == 5:
            return BLOCK
        if op == 6:
            return 0


print("=" * 60)
print("PROTOGON EEPROM TEST + STARFIELD FLASH  (port %d, raw I2C)" % PORT)
print("=" * 60)

# 1. payload
try:
    app_src = open(APP_PAYLOAD).read()
except OSError:
    die("no app payload at %s." % APP_PAYLOAD,
        "Run: mpremote cp app_slim.py :starfield_payload.py + run flash_raw.py")
try:
    compile(app_src, "app.py", "exec")
except SyntaxError as e:
    die("app.py does not compile on this badge: %r" % e)
print("1. payload OK: app.py %d bytes" % len(app_src))

# 2. find the chip
devices = i2c.scan()
if EEPROM_ADDR not in devices:
    die("no EEPROM at 0x50 on port %d (scan: %r)." % (PORT, devices))
print("   EEPROM at 0x50 (bus scan: %s)" % str(devices))

# 3. exhaustive cell test: write + verify every byte, two patterns
print("2. EEPROM cell test (write + verify all %d bytes, 2 patterns)" % CHIP)
for pat in (0xAA, 0x55):
    block = bytes([pat]) * PAGE
    for base in range(0, CHIP, PAGE):
        write_page(base, block)
    for base in range(0, CHIP, 256):
        got = read_region(base, 256)
        for k in range(256):
            if got[k] != pat:
                die("bad cell at 0x%04X: wrote 0x%02X, read 0x%02X."
                    % (base + k, pat, got[k]),
                    "This EEPROM is defective or badly soldered -- check the",
                    "0x50 solder joints.")
    print("   pattern 0x%02X verified across the whole chip" % pat)

# 4. header
write_region(0, HEADER)
back = bytes(read_region(0, 32))
if back != HEADER:
    die("header did not read back correctly.",
        "got: %s" % back.hex())
print("3. header written and verified (%r, vid=0xCAFE pid=0x7062)" % FRIENDLY)

# 5. filesystem + app
unmount("/hexpansion_%d" % PORT)
unmount(MOUNT)
part = RawPartition()
vfs.VfsLfs2.mkfs(part)
vfs.mount(part, MOUNT)
st = os.statvfs(MOUNT)
free = st[1] * st[4]
print("4. littlefs formatted: %d bytes free, need ~%d" % (free, len(app_src)))
if len(app_src) + 512 > free:
    unmount(MOUNT)
    die("app.py (%d bytes) does not fit in %d free bytes." % (len(app_src), free))
try:
    with open(MOUNT + "/app.py", "w") as f:
        f.write(app_src)
    with open(MOUNT + "/app.py") as f:
        app_ok = f.read() == app_src
except OSError as e:
    unmount(MOUNT)
    die("writing app.py failed (%r)." % e)
unmount(MOUNT)
if not app_ok:
    die("app.py did not read back byte-for-byte -- EEPROM unreliable.")
print("5. app.py written and read back byte-for-byte")

try:
    os.remove(APP_PAYLOAD)
except OSError:
    pass

print()
print("#" * 60)
print("#  RESULT: PASS -- EEPROM good, starfield flashed.")
print("#" * 60)
print()
print("NOTE: this badge's firmware predates the v1.12.0 EEPROM fix and")
print("cannot read this (or any Zetta-EEPROM) hexpansion without wedging it.")
print("Update the badge firmware (Settings -> System Update) to >= v1.12.0,")
print("then re-insert Protogon: a %r app appears." % FRIENDLY)
