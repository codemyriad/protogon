// serial.js — a WebSerial MicroPython raw-REPL client (mpremote, in the page).
//
// Protocol verified against micropython docs/reference/repl.rst and
// tools/mpremote/transport_serial.py (see the flash feature notes in the
// README). The parts that bite:
//
//   - The badge is 16D0:120E ("TiLDAGON", custom TinyUSB descriptor), NOT
//     the Espressif VID. 303A:1001 is the S3 in bootloader mode.
//   - Buffer RAW BYTES. Raw-paste's window-size/flow bytes (0x80 0x00, 0x01,
//     0x04) are not UTF-8; a TextDecoderStream would mangle them.
//   - Raw-paste has no "OK": the 0x04 after end-of-data is the ack. Classic
//     raw mode (the fallback) is the one that answers "OK".
//   - Each exec leaves the next ">" prompt in the stream on purpose; consume
//     it at the START of the following exec (promptPending), or the whole
//     protocol desynchronizes by one step.
//   - One ctrl-C is often swallowed by the badge's asyncio scheduler: loop
//     interrupt-and-wait rather than firing a single "\r\x03".
//   - ctrl-D in raw mode soft-resets WITHOUT running main.py (dark badge).
//     To restart the firmware: ctrl-B to ">>> ", THEN ctrl-D.

const enc = new TextEncoder();
const dec = new TextDecoder();

export const BADGE_FILTERS = [
  { usbVendorId: 0x16d0, usbProductId: 0x120e }, // Tildagon
  { usbVendorId: 0x303a }, // Espressif — S3 in bootloader mode (diagnosable)
];

export function serialSupported() {
  return !!navigator.serial;
}

export async function requestBadgePort({ anyDevice = false } = {}) {
  return navigator.serial.requestPort(anyDevice ? {} : { filters: BADGE_FILTERS });
}

export class ReplClient {
  constructor(port, { onDebug = () => {} } = {}) {
    this.port = port;
    this.onDebug = onDebug;
    this.buf = new Uint8Array(0);
    this.dead = null; // Error once the read loop ends
    this.promptPending = false; // a raw-REPL ">" is owed to the stream
    this.rawPasteOk = true;
  }

  async open() {
    await this.port.open({ baudRate: 115200 });
    try {
      // MicroPython's TinyUSB CDC gates stdout on DTR. Chromium asserts it on
      // open by default; make it explicit for browsers that don't.
      await this.port.setSignals({ dataTerminalReady: true });
    } catch {
      /* not all transports implement signals (e.g. the QA mock) */
    }
    this.writer = this.port.writable.getWriter();
    this.reader = this.port.readable.getReader();
    this._readLoop();
  }

  async _readLoop() {
    try {
      for (;;) {
        const { value, done } = await this.reader.read();
        if (done) break;
        if (value?.length) {
          const next = new Uint8Array(this.buf.length + value.length);
          next.set(this.buf);
          next.set(value, this.buf.length);
          this.buf = next;
        }
      }
      this.dead = new Error("the badge disconnected");
    } catch (err) {
      this.dead = new Error(`serial read failed: ${err.message}`);
    }
  }

  async close() {
    try {
      await this.reader.cancel();
    } catch {}
    try {
      this.reader.releaseLock();
      this.writer.releaseLock();
    } catch {}
    try {
      await this.port.close();
    } catch {}
  }

  _take(n) {
    const out = this.buf.subarray(0, n);
    this.buf = this.buf.slice(n);
    return out;
  }

  _findSub(needle) {
    const { buf } = this;
    outer: for (let i = 0; i + needle.length <= buf.length; i++) {
      for (let j = 0; j < needle.length; j++) {
        if (buf[i + j] !== needle[j]) continue outer;
      }
      return i;
    }
    return -1;
  }

  async _write(str) {
    await this.writer.write(enc.encode(str));
  }

  async _writeBytes(bytes) {
    await this.writer.write(bytes);
  }

  // Wait until `needle` (string) appears; consume through it and return the
  // bytes before it. The deadline extends while data keeps arriving
  // (ViperIDE's activity-based timeout).
  async _readUntil(needle, timeoutMs = 5000, { onData } = {}) {
    const nb = enc.encode(needle);
    let deadline = performance.now() + timeoutMs;
    let lastLen = this.buf.length;
    let emitted = 0;
    for (;;) {
      const at = this._findSub(nb);
      if (at >= 0) {
        if (onData && at > emitted) onData(this.buf.subarray(emitted, at));
        const before = this._take(at + nb.length).slice(0, at);
        return before;
      }
      if (this.dead) throw this.dead;
      const now = performance.now();
      if (this.buf.length !== lastLen) {
        lastLen = this.buf.length;
        deadline = now + timeoutMs;
        // stream out everything that can no longer be part of the needle
        const safe = Math.max(0, this.buf.length - nb.length);
        if (onData && safe > emitted) {
          onData(this.buf.subarray(emitted, safe));
          emitted = safe;
        }
      }
      if (now > deadline) {
        throw new Error(
          `timed out waiting for ${JSON.stringify(needle)} ` +
            `(got: ${JSON.stringify(dec.decode(this.buf.slice(-80)))})`
        );
      }
      await sleep(10);
    }
  }

  async _readExactly(n, timeoutMs = 5000) {
    const deadline = performance.now() + timeoutMs;
    while (this.buf.length < n) {
      if (this.dead) throw this.dead;
      if (performance.now() > deadline) {
        throw new Error(`timed out reading ${n} bytes`);
      }
      await sleep(5);
    }
    return Uint8Array.from(this._take(n));
  }

  // --- protocol ---------------------------------------------------------------

  // Stop whatever the badge is running (the scheduler) and confirm a friendly
  // ">>> " prompt. Interleaves ctrl-B in case a previous session left the
  // badge sitting at a raw-REPL prompt.
  async interrupt(totalMs = 10000) {
    const rounds = Math.max(1, Math.floor(totalMs / 500));
    for (let i = 0; i < rounds; i++) {
      this.buf = new Uint8Array(0);
      await this._write(i % 3 === 2 ? "\r\x02" : "\x03");
      try {
        await this._readUntil(">>> ", 500);
        return;
      } catch (err) {
        if (this.dead) throw this.dead;
      }
    }
    throw new Error(
      "the badge never answered with a REPL prompt — is something else " +
        "(mpremote, a terminal) holding the port?"
    );
  }

  async enterRaw() {
    await this._write("\r\x01");
    await this._readUntil("raw REPL; CTRL-B to exit\r\n>", 3000);
    this.promptPending = false;
  }

  // Run python source in raw REPL. Returns stdout (string); throws with the
  // device traceback on error. onStdout receives incremental output chunks.
  async exec(code, { timeoutMs = 20000, onStdout } = {}) {
    if (this.promptPending) {
      await this._readUntil(">", 3000);
      this.promptPending = false;
    }
    const data = enc.encode(code);

    let pasted = false;
    if (this.rawPasteOk) {
      await this._write("\x05A\x01");
      const r = await this._readExactly(2, 3000);
      if (r[0] === 0x52 && r[1] === 0x01) {
        // raw-paste accepted: 2-byte little-endian flow-control window
        const w = await this._readExactly(2, 3000);
        const winSize = w[0] | (w[1] << 8);
        let win = winSize;
        let i = 0;
        while (i < data.length) {
          while (win === 0 || this.buf.length > 0) {
            const b = (await this._readExactly(1, timeoutMs))[0];
            if (b === 0x01) win += winSize;
            else if (b === 0x04) {
              await this._writeBytes(Uint8Array.of(0x04));
              throw new Error("the badge aborted the transfer (out of memory?)");
            } else {
              throw new Error(`raw-paste flow control broke (byte 0x${b.toString(16)})`);
            }
          }
          const n = Math.min(win, data.length - i);
          await this._writeBytes(data.subarray(i, i + n));
          win -= n;
          i += n;
        }
        await this._writeBytes(Uint8Array.of(0x04));
        await this._readUntil("\x04", timeoutMs); // received + compiled, now running
        pasted = true;
      } else if (r[0] === 0x52 && r[1] === 0x00) {
        this.rawPasteOk = false; // understood but unsupported
      } else {
        // "ra..." — old firmware echoing the banner; drain it, fall back
        this.rawPasteOk = false;
        await this._readUntil("w REPL; CTRL-B to exit\r\n>", 3000);
      }
    }

    if (!pasted) {
      for (let i = 0; i < data.length; i += 256) {
        await this._writeBytes(data.subarray(i, i + 256));
        await sleep(10);
      }
      await this._writeBytes(Uint8Array.of(0x04));
      const ok = await this._readExactly(2, 5000);
      if (ok[0] !== 0x4f || ok[1] !== 0x4b) {
        throw new Error("the badge did not acknowledge the code (no OK)");
      }
    }

    const out = await this._readUntil("\x04", timeoutMs, { onData: onStdout });
    const err = await this._readUntil("\x04", 5000);
    this.promptPending = true; // the ">" arrives after; next exec consumes it
    if (err.length) {
      const text = dec.decode(err).trim();
      const e = new Error(text.split("\n").slice(-1)[0] || "badge error");
      e.traceback = text;
      throw e;
    }
    return dec.decode(out);
  }

  // Leave raw REPL and soft-reset from the FRIENDLY prompt: this re-runs
  // main.py, so the scheduler + hexpansion manager come back and freshly
  // flashed hexpansions get mounted and launched.
  async rebootFirmware() {
    await this._write("\r\x02");
    await this._readUntil(">>> ", 3000);
    await this._write("\x04");
    try {
      await this._readUntil("soft reboot", 2000);
    } catch {
      /* some builds phrase it differently; the reset already happened */
    }
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
