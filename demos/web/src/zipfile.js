// zipfile.js — a minimal ZIP writer + reader, no dependencies.
//
// The snippet backup wants to be a real .zip of .py files (open it anywhere,
// grab one file, mail it around) — but pulling in a zip library for that is
// silly when the format's happy path is this small. Writer emits STORED
// (uncompressed) entries — Python sources are a few KB, and a backup that
// needs no inflate code to read beats saving bytes. Reader walks the central
// directory and handles STORED plus DEFLATE (via the browser-native
// DecompressionStream), so foreign zips work too.

const te = new TextEncoder();
const td = new TextDecoder();

let CRC_TABLE = null;
function crc32(bytes) {
  if (!CRC_TABLE) {
    CRC_TABLE = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function dosDateTime(ts) {
  const d = new Date(ts || Date.now());
  return {
    time: (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1),
    date: (((d.getFullYear() - 1980) & 0x7f) << 9) | ((d.getMonth() + 1) << 5) | d.getDate(),
  };
}

// files: [{name, text, at?}] -> Blob (application/zip)
export function makeZip(files) {
  const chunks = [];
  const central = [];
  let offset = 0;

  for (const f of files) {
    const nameB = te.encode(f.name);
    const data = te.encode(f.text);
    const crc = crc32(data);
    const { time, date } = dosDateTime(f.at);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); // local file header
    local.setUint16(4, 20, true); // version needed
    local.setUint16(6, 0x0800, true); // flags: UTF-8 names
    local.setUint16(8, 0, true); // method: STORED
    local.setUint16(10, time, true);
    local.setUint16(12, date, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true); // compressed
    local.setUint32(22, data.length, true); // uncompressed
    local.setUint16(26, nameB.length, true);
    local.setUint16(28, 0, true); // extra length
    chunks.push(new Uint8Array(local.buffer), nameB, data);
    central.push({ nameB, crc, size: data.length, offset, time, date });
    offset += 30 + nameB.length + data.length;
  }

  const cdStart = offset;
  for (const e of central) {
    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true); // central directory entry
    cd.setUint16(4, 20, true); // version made by
    cd.setUint16(6, 20, true); // version needed
    cd.setUint16(8, 0x0800, true); // UTF-8 names
    cd.setUint16(10, 0, true); // STORED
    cd.setUint16(12, e.time, true);
    cd.setUint16(14, e.date, true);
    cd.setUint32(16, e.crc, true);
    cd.setUint32(20, e.size, true);
    cd.setUint32(24, e.size, true);
    cd.setUint16(28, e.nameB.length, true);
    // extra/comment/disk/attribute fields stay zero
    cd.setUint32(42, e.offset, true);
    chunks.push(new Uint8Array(cd.buffer), e.nameB);
    offset += 46 + e.nameB.length;
  }

  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); // end of central directory
  end.setUint16(8, central.length, true);
  end.setUint16(10, central.length, true);
  end.setUint32(12, offset - cdStart, true);
  end.setUint32(16, cdStart, true);
  chunks.push(new Uint8Array(end.buffer));

  return new Blob(chunks, { type: "application/zip" });
}

// ArrayBuffer -> [{name, text}]. STORED + DEFLATE entries only.
export async function readZip(buf) {
  const dv = new DataView(buf);
  const u8 = new Uint8Array(buf);

  // End-of-central-directory: scan back past a possible trailing comment.
  let eocd = -1;
  const stop = Math.max(0, buf.byteLength - 22 - 65535);
  for (let i = buf.byteLength - 22; i >= stop; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("not a zip file");

  const count = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  const out = [];
  for (let i = 0; i < count; i++) {
    if (dv.getUint32(p, true) !== 0x02014b50) throw new Error("bad zip directory");
    const method = dv.getUint16(p + 10, true);
    const csize = dv.getUint32(p + 20, true);
    const nameLen = dv.getUint16(p + 28, true);
    const extraLen = dv.getUint16(p + 30, true);
    const commentLen = dv.getUint16(p + 32, true);
    const lho = dv.getUint32(p + 42, true);
    const name = td.decode(u8.subarray(p + 46, p + 46 + nameLen));
    // sizes of name/extra in the LOCAL header can differ from the central one
    const dataStart =
      lho + 30 + dv.getUint16(lho + 26, true) + dv.getUint16(lho + 28, true);
    const comp = u8.slice(dataStart, dataStart + csize);
    let raw;
    if (method === 0) {
      raw = comp;
    } else if (method === 8) {
      raw = new Uint8Array(
        await new Response(
          new Blob([comp]).stream().pipeThrough(new DecompressionStream("deflate-raw"))
        ).arrayBuffer()
      );
    } else {
      throw new Error(`unsupported zip compression method ${method}`);
    }
    out.push({ name, text: td.decode(raw) });
    p += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}
