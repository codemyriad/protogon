// badge-scripts.js — the Python that runs ON the badge over the raw REPL.
//
// Both scripts print machine lines prefixed "!J" (JSON) so the page can parse
// progress out of a stream that also carries firmware noise —
// get_hexpansion_block_devices() and EEPROM() print ioctl/chip-count lines.
//
// The EEPROM logic mirrors the battle-tested eeprom-image/flash_logo.py:
//   - header written in ONE i2c transaction (2 addr bytes + 32 header bytes =
//     one page): the firmware's chunked write_header fails on Zetta parts
//     (badge-2024-software#59).
//   - the ZD24C64A with WP asserted ACKs writes and silently discards them
//     (datasheet 5.5) — no NACK, ack-poll returns instantly. The ONLY way to
//     detect write protection is write + read-back, hence the scan probe
//     (flip the last byte, verify, restore) and the header verify.

// The scan reads the header with a RAW readfrom_mem (repeated START), NOT the
// firmware's read_hexpansion_header. On firmware older than v1.12.0 that
// helper sets the read pointer with an address-write + STOP, which the Zetta
// ZD24C64A reads as the start of a write cycle and NACKs the whole slot bus
// until the board is power-cycled (real-hardware bring-up, 2026-07-06;
// upstream PR #267). Doing our own repeated-START read is safe on every
// firmware. We still report ota.get_version() so the UI can warn: even though
// scanning is safe, an old-firmware badge may already have wedged the slot on
// insert, and it can't MOUNT the result until updated to v1.12.0+.
export const SCAN_SCRIPT = `
import json, struct, time
from machine import I2C
from system.hexpansion.header import HexpansionHeader

try:
    import ota
    _fw = ota.get_version()   # e.g. "v1.12.3"; NOT os.uname() (that's a git hash)
except Exception:
    _fw = None
print("!J" + json.dumps({"fw": _fw}))

def _present(i2c, addr):
    try:
        i2c.readfrom_mem(addr, 0, 1, addrsize=16)  # repeated START, WP-safe
        return True
    except OSError:
        return False

def _ack(i2c, addr):
    for _ in range(500):
        try:
            i2c.writeto(addr, b"\\x00")
            return True
        except OSError:
            time.sleep_ms(1)
    return False

def _rd(i2c, addr, at):
    return i2c.readfrom_mem(addr, at, 1, addrsize=16)[0]

def _wr(i2c, addr, at, val):
    i2c.writeto(addr, struct.pack(">H", at) + bytes([val]))
    return _ack(i2c, addr)

def _probe_writable(i2c, addr, size):
    # A write-protected ZD24C64A ACKs writes and silently drops them, so the
    # only way to tell is: flip the last byte, read it back, then restore.
    last = size - 1
    orig = _rd(i2c, addr, last)
    _wr(i2c, addr, last, orig ^ 0xFF)
    changed = _rd(i2c, addr, last) == (orig ^ 0xFF)
    if changed:
        _wr(i2c, addr, last, orig)
        if _rd(i2c, addr, last) != orig:
            return False  # could not restore: treat as unusable
    return changed

for port in range(1, 7):
    try:
        i2c = I2C(port)
        if not _present(i2c, 0x50):
            continue
        hdr = None
        try:
            hdr = HexpansionHeader.from_bytes(i2c.readfrom_mem(0x50, 0, 32, addrsize=16))
        except Exception:
            pass                    # blank or foreign EEPROM: header stays None
        size = hdr.eeprom_total_size if hdr else 8192
        info = {"port": port, "addr": 0x50, "alen": 2, "size": size,
                "writable": _probe_writable(i2c, 0x50, size)}
        if hdr:
            name = hdr.friendly_name
            if isinstance(name, bytes):
                name = name.decode()
            info["name"] = name.rstrip("\\x00")
            info["vid"] = hdr.vid
            info["pid"] = hdr.pid
        print("!J" + json.dumps(info))
    except Exception as e:
        print("!J" + json.dumps({"port": port, "error": repr(e)}))
print("!J" + json.dumps({"done": True}))
`;

// Tokens __PORT__ __NAME__ __VID__ __PID__ __FNAME__ __B64__ are substituted
// by buildFlashScript(). Plain tokens, not str.format: the script itself
// contains every brace under the sun.
const FLASH_TEMPLATE = `
import binascii, json, os, struct, time, vfs
from machine import I2C
from system.hexpansion.header import HexpansionHeader
from system.hexpansion.util import detect_eeprom_addr, read_hexpansion_header, get_hexpansion_block_devices

PORT = __PORT__
VID = __VID__
PID = __PID__
NAME = __NAME__
FNAME = __FNAME__
PAYLOAD = binascii.a2b_base64("__B64__")
MP = "/protogon_web_flash"

def J(**kw):
    print("!J" + json.dumps(kw))

class Fail(Exception):
    pass

def fail(stage, msg):
    J(stage=stage, ok=False, error=msg)
    raise Fail(msg)

def ack(i2c, addr):
    for _ in range(500):
        try:
            i2c.writeto(addr, b"\\x00")
            return True
        except OSError:
            time.sleep_ms(1)
    return False

def unmount(path):
    try:
        vfs.umount(path)
    except OSError:
        pass

try:
    i2c = I2C(PORT)
    addr, alen = detect_eeprom_addr(i2c)
    if addr is None:
        fail("detect", "no EEPROM found on port %d" % PORT)
    if alen != 2:
        fail("detect", "1-byte-addressed EEPROM; not a Protogon, refusing")
    J(stage="detect", ok=True, addr=addr)

    if FNAME.endswith(".py"):
        try:
            compile(PAYLOAD.decode(), "app.py", "exec")
        except SyntaxError as e:
            fail("compile", "does not compile on the badge: %r" % e)
        J(stage="compile", ok=True)

    hdr = HexpansionHeader(
        manifest_version="2024",
        fs_offset=32,
        eeprom_page_size=32,
        eeprom_total_size=8192,
        vid=VID,
        pid=PID,
        unique_id=0,
        friendly_name=NAME,
    )

    unmount("/hexpansion_%d" % PORT)  # the OS may have mounted it pre-interrupt
    unmount(MP)

    try:
        i2c.writeto(addr, bytes([0, 0]) + hdr.to_bytes())
    except OSError:
        fail("header", "EEPROM NACKed the header write - reseat the board?")
    if not ack(i2c, addr):
        fail("header", "header write never completed")
    back = i2c.readfrom_mem(addr, 0, 32, addrsize=16)
    if bytes(back[1:]) != hdr.to_bytes()[1:]:
        fail("header", "header did not stick - P1 write-protect jumper shorted?")
    J(stage="header", ok=True)

    eep, part = get_hexpansion_block_devices(i2c, hdr, addr, addr_len=alen)
    vfs.VfsLfs2.mkfs(part)
    vfs.mount(part, MP)
    st = os.statvfs(MP)
    free = st[1] * st[4]
    J(stage="format", ok=True, free=free)
    if len(PAYLOAD) + 512 > free:
        unmount(MP)
        fail("space", "%d bytes do not fit in %d free" % (len(PAYLOAD), free))

    with open(MP + "/" + FNAME, "wb") as f:
        f.write(PAYLOAD)
    with open(MP + "/" + FNAME, "rb") as f:
        good = f.read() == PAYLOAD
    unmount(MP)
    if not good:
        fail("readback", "file did not read back byte-for-byte - EEPROM unreliable")
    J(stage="write", ok=True, bytes=len(PAYLOAD))
    J(stage="done", ok=True)
except Fail:
    pass
`;

const pyStr = (s) => JSON.stringify(s); // ascii double-quoted: valid Python too

export function buildFlashScript({ port, name, vid, pid, fname, payload }) {
  let b64 = "";
  for (let i = 0; i < payload.length; i += 0x8000) {
    b64 += String.fromCharCode(...payload.subarray(i, i + 0x8000));
  }
  b64 = btoa(b64);
  // Function replacements: a literal "$" in the value (a name like "a$b", or
  // base64) would otherwise be read as a replace() special pattern ($&, $$, …)
  // and corrupt the generated Python.
  return FLASH_TEMPLATE.replace("__PORT__", () => String(port))
    .replace("__VID__", () => `0x${vid.toString(16)}`)
    .replace("__PID__", () => `0x${pid.toString(16)}`)
    .replace("__NAME__", () => pyStr(name))
    .replace("__FNAME__", () => pyStr(fname))
    .replace("__B64__", () => b64);
}

// Parse "!J{...}" lines out of a stdout stream that also carries firmware
// noise. Returns objects in order; tolerates partial trailing lines via the
// carry mechanism (feed() keeps the last unterminated line).
export function jsonLineParser(onEvent) {
  let carry = "";
  return (chunkText) => {
    carry += chunkText;
    const lines = carry.split("\n");
    carry = lines.pop();
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("!J")) continue;
      try {
        onEvent(JSON.parse(t.slice(2)));
      } catch {
        /* mangled line: ignore */
      }
    }
  };
}
