# flash_logo.py
#
# Two jobs in one command:
#   1. Validate the EEPROM on a freshly produced Protogon (write/verify every
#      cell, then verify the flashed files read back byte-for-byte). Prints a
#      clear PASS / FAIL you can act on at a test bench.
#   2. Leave the board with a working demo app: it shows the Codemyriad logo
#      on the badge screen whenever Protogon is inserted.
#
# Run it from this directory with Protogon in a slot and the badge on USB-IN:
#
#     mpremote cp app.py :logo_app_payload.py + cp logo.dat :logo_data_payload.dat + run flash_logo.py
#
# then reboot the badge (`mpremote reset`) or re-insert Protogon.
#
# Needs the P1 jumper OPEN (P1 shorted = EEPROM write-protected). Runs entirely
# from RAM on stock firmware -- nothing is installed on the badge.

# --------------------------- configuration -------------------------------
PORT = 1          # hexpansion slot Protogon is in: 1..6, clockwise from the
                  # upper-right slot (the one above the USB-OUT connector)
VID = 0xCAFE      # 0xCAFE = the community "open to everyone" vendor id
PID = 0x7061      # this app's product id (distinct from other Protogon apps)
FRIENDLY = "Protogon"   # badge notification on insert; max 9 characters
FULL_TEST = True  # exhaustive cell test (write+verify all 8 KiB, ~a few s).
                  # Set False for a quick flash that only verifies the files.
FORCE = False     # overwrite an existing valid header without asking

APP_PAYLOAD = "/logo_app_payload.py"    # where `mpremote cp` put app.py
LOGO_PAYLOAD = "/logo_data_payload.dat"  # ...and logo.dat
# --------------------------------------------------------------------------

import os
import struct
import time
import vfs
from machine import I2C
from system.hexpansion.header import HexpansionHeader
from system.hexpansion.util import (
    detect_eeprom_addr,
    get_hexpansion_block_devices,
    read_hexpansion_header,
)

CHIP = 8192       # ZD24C64A: 64 kbit
PAGE = 32         # write-page size
MOUNT = "/protogon_flash"


def die(*lines):
    print()
    print("#" * 60)
    print("#  RESULT: FAIL")
    for ln in lines:
        print("#  " + ln)
    print("#" * 60)
    raise SystemExit


def slim(src):
    """Drop full-line comments and repeated blanks so app.py fits the EEPROM.
    Left whole if it contains triple-quoted strings (a '#' line inside one
    would be data, not a comment)."""
    if '"""' in src or "'''" in src:
        return src
    out = []
    blank = False
    for line in src.split("\n"):
        s = line.strip()
        if s.startswith("#"):
            continue
        if not s:
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(line.rstrip())
    return "\n".join(out).lstrip("\n") + "\n"


def unmount(path):
    try:
        vfs.umount(path)
    except OSError:
        pass


# --- raw EEPROM access (no driver dependency, so the cell test is exact) ---
def ack_poll(i2c, addr):
    # After a page write the chip NACKs its address until the internal write
    # cycle finishes; a bare 1-byte write that ACKs means it is ready again.
    for _ in range(500):
        try:
            i2c.writeto(addr, b"\x00")
            return True
        except OSError:
            time.sleep_ms(1)
    return False


def write_page(i2c, addr, memaddr, chunk):
    try:
        i2c.writeto(addr, struct.pack(">H", memaddr) + chunk)
    except OSError:
        die("EEPROM NACKed a write at 0x%04X." % memaddr,
            "The 0x50 EEPROM is not responding: check Protogon is seated, the",
            "0x50 solder joints, and that the P1 jumper is OPEN (P1 shorted =",
            "write-protected).")
    if not ack_poll(i2c, addr):
        die("EEPROM never finished a write at 0x%04X." % memaddr,
            "The chip is most likely write-protected: OPEN the P1 jumper and",
            "run again. (P1 shorted = write-protected.)")


def write_region(i2c, addr, start, data):
    off = 0
    while off < len(data):
        memaddr = start + off
        room = PAGE - (memaddr % PAGE)          # never cross a page boundary
        n = room if (len(data) - off) > room else (len(data) - off)
        write_page(i2c, addr, memaddr, data[off:off + n])
        off += n


def read_region(i2c, addr, start, n):
    return i2c.readfrom_mem(addr, start, n, addrsize=16)


def cell_test(i2c, addr):
    """Write two complementary patterns to every byte and read them back.
    Catches stuck bits and bad cells anywhere in the array."""
    print("2. EEPROM cell test (write + verify all %d bytes)" % CHIP)
    for pat in (0xAA, 0x55):
        block = bytes([pat]) * PAGE
        for base in range(0, CHIP, PAGE):
            write_page(i2c, addr, base, block)
        for base in range(0, CHIP, 256):
            got = read_region(i2c, addr, base, 256)
            for k in range(256):
                if got[k] != pat:
                    die("bad cell at 0x%04X: wrote 0x%02X, read 0x%02X."
                        % (base + k, pat, got[k]),
                        "This EEPROM is defective or badly soldered -- reject",
                        "the board (or check the 0x50 solder joints).")
        print("   pattern 0x%02X verified across the whole chip" % pat)


print("=" * 60)
print("PROTOGON EEPROM FLASH + TEST  (port %d)" % PORT)
print("=" * 60)

if len(FRIENDLY) > 9:
    die("FRIENDLY (%r) is %d characters; the header field holds 9."
        % (FRIENDLY, len(FRIENDLY)))

# 1. payloads ----------------------------------------------------------------
try:
    app_src = slim(open(APP_PAYLOAD).read())
except OSError:
    die("no app payload at %s." % APP_PAYLOAD,
        "Run: mpremote cp app.py :logo_app_payload.py + cp logo.dat"
        " :logo_data_payload.dat + run flash_logo.py")
try:
    compile(app_src, "app.py", "exec")
except SyntaxError as e:
    die("app.py does not compile on this badge: %r" % e)
try:
    logo = open(LOGO_PAYLOAD, "rb").read()
except OSError:
    die("no logo payload at %s (copy logo.dat too -- see the command above)."
        % LOGO_PAYLOAD)
if logo[:4] != b"PLG1":
    die("logo.dat has a bad magic (%r); regenerate it with tools/make_logo.py."
        % logo[:4])
print("1. payloads OK: app.py %d bytes, logo.dat %d bytes" % (len(app_src), len(logo)))

# 2. find the EEPROM ---------------------------------------------------------
i2c = I2C(PORT)
addr, addr_len = detect_eeprom_addr(i2c)
if addr is None:
    die("no EEPROM found on port %d." % PORT,
        "Is Protogon seated in that slot? Set PORT at the top of this file to",
        "the slot you used (1..6 clockwise from the upper-right).")
if addr_len != 2:
    die("found a %d-byte-addressed EEPROM; Protogon's ZD24C64A is 2-byte."
        % addr_len, "This looks like a different hexpansion -- aborting.")
print("   EEPROM at %s, 2-byte addressing" % hex(addr))

existing = read_hexpansion_header(i2c, addr, addr_len=addr_len)
if existing is not None and not FORCE and not FULL_TEST:
    die("this EEPROM already has a valid header (%r). Set FORCE = True to"
        % existing.friendly_name, "overwrite, or FULL_TEST = True to re-test and reflash.")

# 3. cell test (optional) ----------------------------------------------------
if FULL_TEST:
    cell_test(i2c, addr)
else:
    print("2. cell test skipped (FULL_TEST = False)")

# 4. header ------------------------------------------------------------------
header = HexpansionHeader(
    manifest_version="2024",
    fs_offset=32,
    eeprom_page_size=PAGE,
    eeprom_total_size=CHIP,
    vid=VID,
    pid=PID,
    unique_id=0,
    friendly_name=FRIENDLY,
)
# One 34-byte transaction (2 address bytes + 32 header bytes = one page). The
# firmware's chunked write_header fails on Zetta parts like ours (badge-2024-
# software#59); this single-page write is the documented workaround.
try:
    i2c.writeto(addr, bytes([0, 0]) + header.to_bytes())
except OSError:
    die("the EEPROM NACKed the header write.",
        "Usually P1 is shorted (write-protected) or Protogon isn't making",
        "contact. Open P1, reseat the board, and retry.")
if not ack_poll(i2c, addr):
    die("header write never completed -- OPEN the P1 jumper and retry.")
back = read_hexpansion_header(i2c, addr, addr_len=addr_len)
if back is None or back.to_bytes() != header.to_bytes():
    die("header did not read back correctly.",
        "Usually the P1 jumper is shorted (write-protected). Open it and retry.")
print("3. header written and verified (%r, vid=0x%04X pid=0x%04X)"
      % (FRIENDLY, VID, PID))

# 5. filesystem + files ------------------------------------------------------
unmount("/hexpansion_%d" % PORT)   # the OS may have auto-mounted it on insert
unmount(MOUNT)
eep, partition = get_hexpansion_block_devices(i2c, header, addr, addr_len=addr_len)
vfs.VfsLfs2.mkfs(partition)
vfs.mount(partition, MOUNT)
st = os.statvfs(MOUNT)
free = st[1] * st[4]
need = len(app_src) + len(logo)
print("4. filesystem formatted: %d bytes free, need ~%d" % (free, need))
if need + 512 > free:
    unmount(MOUNT)
    die("app.py + logo.dat (%d bytes) do not fit in %d free bytes." % (need, free),
        "Shrink the logo (tools/make_logo.py, lower resolution) or the app.")

try:
    with open(MOUNT + "/app.py", "w") as f:
        f.write(app_src)
    with open(MOUNT + "/logo.dat", "wb") as f:
        f.write(logo)
    # read-back verification -- this is the file-level EEPROM proof
    with open(MOUNT + "/app.py") as f:
        app_ok = f.read() == app_src
    with open(MOUNT + "/logo.dat", "rb") as f:
        logo_ok = f.read() == logo
except OSError as e:
    unmount(MOUNT)
    die("writing the files failed (%r)." % e,
        "If this is ENOSPC the payload is too big; otherwise open P1 and retry.")
unmount(MOUNT)
if not (app_ok and logo_ok):
    die("a file did not read back byte-for-byte (app_ok=%s logo_ok=%s)."
        % (app_ok, logo_ok), "The EEPROM is unreliable -- reject the board.")

for p in (APP_PAYLOAD, LOGO_PAYLOAD):
    try:
        os.remove(p)
    except OSError:
        pass

print("5. app.py + logo.dat written and verified byte-for-byte")
print()
print("#" * 60)
print("#  RESULT: PASS -- EEPROM good, logo app flashed.")
print("#" * 60)
print()
print("Reboot the badge (mpremote reset) or re-insert Protogon: it shows a")
print("%r notification and the Codemyriad logo appears on screen." % FRIENDLY)
print("Optional: short P1 to write-protect the EEPROM for the field.")
