// mockserial.js — a fake Tildagon on a fake serial port, for headless QA of
// the flash dialog. Speaks just enough of the raw REPL + raw-paste protocol
// to exercise every code path in serial.js: interrupt, banner, flow-control
// windows, "!J" progress streaming, WP failure.
//
//   ?mockserial=1     firmware v1.12.3 (fine)
//   ?mockserial=old   firmware v1.10.0 (triggers the update-firmware warning)
//
// The fake badge has two hexpansions plugged in:
//   port 2: blank EEPROM, writable       (the happy path)
//   port 5: "Protogon" header, P1 shorted (flash fails at the header verify)

const enc = new TextEncoder();

function scanResult(mode) {
  return [
    { fw: mode === "old" ? "v1.10.0" : "v1.12.3" },
    { port: 2, addr: 0x50, alen: 2, size: 8192, writable: true },
    { port: 5, addr: 0x50, alen: 2, size: 8192, writable: false,
      name: "Protogon", vid: 0xcafe, pid: 0x7061 },
    { done: true },
  ];
}

export function createMockPort() {
  const mode = new URLSearchParams(location.search).get("mockserial");
  const SCAN_RESULT = scanResult(mode);
  let out = null; // ReadableStream controller
  const emit = (s) => out?.enqueue(typeof s === "string" ? enc.encode(s) : s);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const WINDOW = 128;
  const state = {
    mode: "friendly", // friendly | raw | paste
    pending: [], // bytes not yet interpreted
    paste: null, // {collected: [], since: 0}
  };

  async function runScript(src) {
    if (src.includes("_probe_writable")) {
      for (const line of SCAN_RESULT) {
        await sleep(60);
        emit("!J" + JSON.stringify(line) + "\r\n");
      }
      return;
    }
    const portMatch = src.match(/^PORT = (\d+)/m);
    if (portMatch) {
      const port = Number(portMatch[1]);
      const isPy = src.includes('"app.py"') && !src.includes('"app.mpy"');
      const b64 = src.match(/a2b_base64\("([^"]*)"\)/)?.[1] || "";
      const bytes = Math.floor((b64.length * 3) / 4);
      const J = (o) => emit("!J" + JSON.stringify(o) + "\r\n");
      await sleep(80);
      J({ stage: "detect", ok: true, addr: 0x50 });
      if (isPy) {
        await sleep(60);
        J({ stage: "compile", ok: true });
      }
      await sleep(120);
      if (port === 5) {
        J({ stage: "header", ok: false,
            error: "header did not stick - P1 write-protect jumper shorted?" });
        return;
      }
      J({ stage: "header", ok: true });
      emit("4 ioctl 5\r\n"); // firmware noise the parser must ignore
      await sleep(200);
      J({ stage: "format", ok: true, free: 6656 });
      await sleep(250);
      J({ stage: "write", ok: true, bytes });
      J({ stage: "done", ok: true });
    }
  }

  // Run the collected program, then close out the exec exactly like a real
  // badge: stdout 0x04, (empty) stderr 0x04, ">" prompt. NOT awaited by feed()
  // so the write() that sent the final 0x04 resolves immediately and the
  // client is already in _readUntil when output streams — exercising the
  // incremental onStdout path.
  function finishExec(src) {
    runScript(src).then(() => {
      emit("\x04"); // end of stdout
      emit("\x04"); // empty error section
      emit(">");
    });
  }

  const noRawPaste = mode === "classic" || mode === "old";

  async function feed(chunk) {
    for (const b of chunk) {
      if (state.mode === "paste") {
        if (b === 0x04) {
          const src = new TextDecoder().decode(Uint8Array.from(state.paste.collected));
          state.paste = null;
          state.mode = "raw";
          emit("\x04"); // ack: received + compiled
          finishExec(src);
          continue;
        }
        state.paste.collected.push(b);
        if (++state.paste.since >= WINDOW) {
          state.paste.since = 0;
          emit("\x01"); // free another flow-control window
        }
        continue;
      }
      // Classic raw mode: collect code bytes until 0x04, reply "OK", then run.
      if (state.mode === "classic") {
        if (b === 0x04) {
          const src = new TextDecoder().decode(Uint8Array.from(state.paste.collected));
          state.paste = null;
          state.mode = "raw";
          emit("OK");
          finishExec(src);
          continue;
        }
        state.paste.collected.push(b);
        continue;
      }
      // Once raw-paste is off, an exec after the first sends raw code with no
      // \x05A\x01 probe. In raw mode, a non-control byte at the START of a
      // sequence (pending empty, so not the 'A' inside a \x05A\x01 probe)
      // begins classic code.
      if (state.mode === "raw" && noRawPaste && b > 0x05 && state.pending.length === 0) {
        state.mode = "classic";
        state.paste = { collected: [b] };
        continue;
      }
      state.pending.push(b);
    }

    // Interpret control sequences outside paste/classic mode.
    const text = String.fromCharCode(...state.pending);
    if (text.includes("\x05A\x01") && state.mode === "raw") {
      state.pending = [];
      if (noRawPaste) {
        // Understood but unsupported: the client must fall back to classic raw.
        state.mode = "classic";
        state.paste = { collected: [], since: 0 };
        emit("R\x00");
      } else {
        state.mode = "paste";
        state.paste = { collected: [], since: 0 };
        emit("R\x01");
        emit(Uint8Array.of(WINDOW & 0xff, WINDOW >> 8));
      }
    } else if (text.includes("\x01")) {
      state.pending = [];
      state.mode = "raw";
      emit("\r\nraw REPL; CTRL-B to exit\r\n>");
    } else if (text.includes("\x02")) {
      state.pending = [];
      state.mode = "friendly";
      emit("\r\n>>> ");
    } else if (text.includes("\x03")) {
      state.pending = [];
      if (state.mode === "friendly") {
        emit("\r\nKeyboardInterrupt\r\n>>> ");
      } else {
        emit("\r\n>");
      }
    } else if (text.includes("\x04")) {
      state.pending = [];
      if (state.mode === "friendly") {
        emit("MPY: soft reboot\r\n[mock badge] scheduler up, hexpansions mounted\r\n");
      }
    } else if (state.pending.length > 64) {
      state.pending = [];
    }
  }

  return {
    readable: new ReadableStream({
      start(c) {
        out = c;
      },
    }),
    writable: new WritableStream({
      async write(chunk) {
        await feed(chunk);
      },
    }),
    async open() {},
    async close() {
      try {
        out?.close();
      } catch {}
    },
    async setSignals() {},
    getInfo: () => ({ usbVendorId: 0x16d0, usbProductId: 0x120e }),
  };
}
