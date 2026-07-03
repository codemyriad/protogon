# provision_protogon.py
#
# Put the Protogon thermal-viewer app onto the hexpansion's ID EEPROM, so the
# badge auto-launches it whenever Protogon is inserted. One command, run from
# this directory with Protogon in a slot and the badge on its USB-IN port:
#
#     mpremote cp app.py :protogon_app_payload.py + run provision_protogon.py
#
# then reboot the badge (`mpremote reset`, or eject and re-insert Protogon).
#
# What it does, in order:
#   1. sanity-check the app payload (compiles it with the badge's own Python)
#   2. find the ID EEPROM (0x50) on the chosen port
#   3. write the 32-byte hexpansion identity header    (skipped if APP_ONLY)
#   4. format the EEPROM's little filesystem           (skipped if APP_ONLY)
#   5. copy the app in (comment lines stripped so it fits 8 KiB), verify it
#
# It needs the P1 jumper OPEN (P1 shorted = EEPROM write-protected). It runs
# entirely from RAM on the badge's stock firmware -- nothing is installed.

# --------------------------- configuration -------------------------------
PORT = 1          # hexpansion slot Protogon is in: 1..6, clockwise from the
                  # upper-right slot (the one above the USB-OUT connector)
VID = 0xCAFE      # 0xCAFE = the "open to everyone" vendor id. Register your
PID = 0x7060      # own pid via an issue at github.com/emfcamp/hexpansion-firmwares
FRIENDLY = "Protogon"   # shown as a badge notification on insert; max 9 chars
FORCE = False     # True: overwrite an existing valid header + reformat
APP_ONLY = False  # True: keep the header + filesystem, only replace app.py

PAYLOAD = "/protogon_app_payload.py"   # where the `mpremote cp` above put it
# --------------------------------------------------------------------------

import os
import time
import vfs
from machine import I2C
from system.hexpansion.header import HexpansionHeader
from system.hexpansion.util import (
    detect_eeprom_addr,
    get_hexpansion_block_devices,
    read_hexpansion_header,
)

MOUNT = "/protogon_provision"


def die(*lines):
    print()
    for ln in lines:
        print("!! " + ln)
    raise SystemExit


def slim(src):
    """Drop full-line comments and repeated blanks. app.py is ~6.6 KB with
    its comments and the filesystem holds ~6.5 KB, so installing the
    commented file would overflow the EEPROM; stripped it is ~6 KB. Code
    lines are untouched, and sources containing triple-quoted strings are
    left whole (a '#' line inside one would be data, not a comment)."""
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


print("=" * 60)
print("PROTOGON EEPROM PROVISIONING  (port %d)" % PORT)
print("=" * 60)

if len(FRIENDLY) > 9:
    die("FRIENDLY (%r) is %d characters; the header field holds at most 9."
        % (FRIENDLY, len(FRIENDLY)))

# 1. payload -----------------------------------------------------------------
try:
    src = open(PAYLOAD).read()
except OSError:
    die("no app payload at %s." % PAYLOAD,
        "Run exactly:  mpremote cp app.py :%s + run provision_protogon.py"
        % PAYLOAD.lstrip("/"))
src = slim(src)
try:
    compile(src, "app.py", "exec")
except SyntaxError as e:
    die("app.py does not compile on this badge: %r" % e)
print("1. app payload OK: %d bytes after comment-stripping" % len(src))

# 2. find the EEPROM ----------------------------------------------------------
i2c = I2C(PORT)
found = i2c.scan()
print("2. i2c scan on port %d: %s" % (PORT, [hex(a) for a in found]))
addr, addr_len = detect_eeprom_addr(i2c)
if addr is None:
    die("no EEPROM found on port %d." % PORT,
        "Is Protogon seated in that slot? Set PORT at the top of this",
        "file to the slot you used (1..6 clockwise from upper-right).")
print("   EEPROM at %s (%d-byte addressing)" % (hex(addr), addr_len))
if addr_len != 2:
    die("found a %d-byte-addressed EEPROM; Protogon's ZD24C64A uses 2-byte" % addr_len,
        "addressing. This looks like a different hexpansion -- aborting",
        "before writing anything.")

existing = read_hexpansion_header(i2c, addr, addr_len=addr_len)

# 3. header -------------------------------------------------------------------
if APP_ONLY:
    if existing is None:
        die("APP_ONLY = True but there is no valid header yet.",
            "Run once with APP_ONLY = False first.")
    header = existing
    print("3. keeping the existing header (%s / vid=0x%04X pid=0x%04X)"
          % (existing.friendly_name, existing.vid, existing.pid))
else:
    if existing is not None and not FORCE:
        die("this EEPROM already has a valid header:",
            "  name=%r vid=0x%04X pid=0x%04X"
            % (existing.friendly_name, existing.vid, existing.pid),
            "Set FORCE = True to overwrite it (and reformat the filesystem),",
            "or APP_ONLY = True to only replace the app.")
    header = HexpansionHeader(
        manifest_version="2024",   # accepted by 2024 and 2026 firmware
        fs_offset=32,
        eeprom_page_size=32,
        eeprom_total_size=8192,    # ZD24C64A: 64 kbit
        vid=VID,
        pid=PID,
        unique_id=0,
        friendly_name=FRIENDLY,
    )
    # Write header as ONE 34-byte transaction (2 address bytes + 32 bytes =
    # exactly one EEPROM page). The firmware's chunked write_header() is known
    # to fail on Zetta parts like ours (badge-2024-software issue #59); this
    # single-page write is the officially documented workaround.
    i2c.writeto(addr, bytes([0, 0]) + header.to_bytes())
    for _ in range(100):           # ACK-poll the EEPROM's internal write cycle
        try:
            i2c.writeto(addr, bytes([0]))
            break
        except OSError:
            time.sleep_ms(1)
    readback = read_hexpansion_header(i2c, addr, addr_len=addr_len)
    if readback is None or readback.to_bytes() != header.to_bytes():
        die("header did not stick after writing.",
            "Almost always this means the EEPROM is write-protected:",
            "REMOVE the P1 jumper (P1 shorted = write-protected) and re-run.")
    print("3. header written and verified (%r, vid=0x%04X pid=0x%04X)"
          % (FRIENDLY, VID, PID))

# 4. filesystem ---------------------------------------------------------------
# The badge OS may have already mounted this EEPROM at /hexpansion_N when the
# hexpansion was inserted; unmount everywhere before touching the partition.
unmount("/hexpansion_%d" % PORT)
unmount(MOUNT)
eep, partition = get_hexpansion_block_devices(i2c, header, addr, addr_len=addr_len)
if not APP_ONLY:
    vfs.VfsLfs2.mkfs(partition)
    print("4. littlefs formatted")
else:
    print("4. keeping the existing filesystem")
vfs.mount(partition, MOUNT)
if APP_ONLY:
    try:
        os.remove(MOUNT + "/app.py")   # the replacement reuses this space,
    except OSError:                    # so measure free space without it
        pass
st = os.statvfs(MOUNT)
free = st[1] * st[4]
print("   filesystem: %d bytes free (block size %d)" % (free, st[0]))

# 5. install the app ----------------------------------------------------------
# littlefs needs a little slack for file metadata, so demand some headroom.
if len(src) + 256 > free:
    unmount(MOUNT)
    die("app.py (%d bytes + ~256 overhead) does not fit in the %d free bytes."
        % (len(src), free),
        "Trim the app (every code line costs EEPROM), or compile it with",
        "mpy-cross and adapt PAYLOAD -- see README.md, 'If it does not fit'.")
try:
    with open(MOUNT + "/app.py", "w") as f:
        f.write(src)
    with open(MOUNT + "/app.py") as f:
        ok = f.read() == src
except OSError as e:
    unmount(MOUNT)
    die("writing app.py failed (%r)." % e,
        "If this is ENOSPC (errno 28) the app is too big -- see README.md,",
        "'If it does not fit'. Otherwise re-run with FORCE = True and check",
        "that the P1 jumper is open.")
unmount(MOUNT)
if not ok:
    die("read-back of app.py did not match what was written.",
        "If the P1 jumper is open, re-run with FORCE = True; if it keeps",
        "failing, re-run the bus diagnostic in ../diagnostics/.")
try:
    os.remove(PAYLOAD)             # tidy the badge's internal flash
except OSError:
    pass

print("5. app installed and verified")
print()
print("DONE. Now reboot the badge:  mpremote reset")
print("(or eject and re-insert Protogon). The badge shows a %r" % FRIENDLY)
print("notification and the thermal viewer starts on its own.")
print("Optional: short P1 again to write-protect the EEPROM.")
