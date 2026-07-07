// flash.js — "put this program on a real hexpansion", from the browser.
//
// Flow: WebSerial connect -> interrupt the badge scheduler -> raw REPL ->
// scan all 6 hexpansion ports for EEPROMs (writability probed by actually
// flipping a byte: a write-protected ZD24C64A ACKs and silently ignores
// writes, so only read-back tells the truth) -> user picks a port + format
// (.py stripped, or .mpy compiled in-browser) -> flash script streams "!J"
// progress -> soft reset from the friendly REPL so main.py runs again and
// the badge mounts + launches the new hexpansion.
//
// ?mockserial=1 swaps the real port for src/mockserial.js so all of this is
// testable in CI without hardware.

import { serialSupported, requestBadgePort, ReplClient } from "./serial.js";
import { SCAN_SCRIPT, buildFlashScript, jsonLineParser } from "./badge-scripts.js";
import { slimPython, EEPROM_BUDGET } from "./library.js";
import { createMockPort } from "./mockserial.js";
import { compileMpy } from "./mpy.js";

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// vid/pid social contract (emfcamp/hexpansion-firmwares): 0xCAFE is the
// "open to everyone" vendor; a pid is a hexpansion *type*, and the launcher
// shows the friendly_name (not the pid) to humans. So every program flashed
// from the playground is the same "type" — a personal experiment — and shares
// ONE pid; the name you give it is what tells them apart. 0x7063 is currently
// unregistered, so the badge's "Update firmware" button can never pull a
// download over it. (If you build a real, distributable hexpansion, claim your
// own pid at github.com/emfcamp/hexpansion-firmwares and set it below.)
const DEFAULT_VID = 0xcafe;
const DEFAULT_PID = 0x7063;

// The badge firmware fix that lets our Zetta EEPROM be read without wedging
// the slot bus shipped in v1.12.0 (badge-2024-software PR #267).
const MIN_FIRMWARE = [1, 12, 0];

// "v1.12.3" -> [1,12,3]; returns null if unparseable.
function parseVersion(s) {
  const m = /v?(\d+)\.(\d+)\.(\d+)/.exec(String(s || ""));
  return m ? [+m[1], +m[2], +m[3]] : null;
}
function versionBelow(v, min) {
  for (let i = 0; i < 3; i++) {
    if (v[i] < min[i]) return true;
    if (v[i] > min[i]) return false;
  }
  return false;
}

export function initFlash({ getCode, getName }) {
  const dialog = $("#flash-dialog");
  const mock = new URLSearchParams(location.search).has("mockserial");

  const state = {
    phase: "idle",
    client: null,
    interrupted: false, // we stopped the scheduler: owe the badge a reboot
    firmware: undefined, // reported version string, or null if unknown
    devices: [],
    code: "",
    slim: "",
    mpy: null, // Uint8Array | null
    mpyError: null,
    chosen: null,
    // The form lives in state, not the DOM: render() rebuilds the dialog's
    // innerHTML on every selection, so reading inputs back at flash time would
    // get the freshly-defaulted values, not what the user typed/picked.
    form: { name: "myapp", fmt: "py", vid: hex4(DEFAULT_VID), pid: hex4(DEFAULT_PID) },
    log: [],
  };

  // --- helpers -----------------------------------------------------------------

  function setPhase(phase) {
    state.phase = phase;
    render();
  }

  function logLine(text, cls = "") {
    state.log.push({ text, cls });
    if (state.phase === "flashing" || state.phase === "scanning") render();
  }

  async function cleanup({ reboot = true } = {}) {
    const { client } = state;
    state.client = null;
    if (!client) return;
    if (reboot && state.interrupted) {
      try {
        await client.rebootFirmware();
      } catch {
        /* best effort: never leave without trying to revive the badge */
      }
    }
    state.interrupted = false;
    await client.close();
  }

  function appName() {
    return (
      (getName() || "myapp").replace(/[^\x20-\x7e]/g, "").trim().slice(0, 9) || "myapp"
    );
  }

  // --- connect + scan -----------------------------------------------------------

  async function connectAndScan(anyDevice) {
    try {
      setPhase("connecting");
      let port;
      if (mock) {
        port = createMockPort();
      } else {
        try {
          port = await requestBadgePort({ anyDevice });
        } catch {
          setPhase("pickport"); // user dismissed the chooser
          return;
        }
      }
      state.client = new ReplClient(port);
      await state.client.open();

      state.log = [];
      setPhase("scanning");
      logLine("stopping the badge scheduler…");
      await state.client.interrupt();
      state.interrupted = true;
      await state.client.enterRaw();
      logLine("scanning hexpansion ports 1–6…");

      state.devices = [];
      state.firmware = undefined;
      const parse = jsonLineParser((ev) => {
        if (ev.done) return;
        if ("fw" in ev) {
          state.firmware = ev.fw;
          const v = parseVersion(ev.fw);
          if (v && versionBelow(v, MIN_FIRMWARE)) {
            logLine(`badge firmware ${ev.fw} is too old (need v1.12.0+)`, "err");
          } else {
            logLine(`badge firmware ${ev.fw || "unknown"}`);
          }
        } else if (ev.error) logLine(`port ${ev.port}: ${ev.error}`, "err");
        else state.devices.push(ev);
      });
      const dec = new TextDecoder();
      await state.client.exec(SCAN_SCRIPT, {
        timeoutMs: 30000,
        onStdout: (bytes) => parse(dec.decode(bytes, { stream: true })),
      });
      setPhase("pick");
    } catch (err) {
      fail(err);
    }
  }

  // --- flash ---------------------------------------------------------------------

  async function flash() {
    const dev = state.devices.find((d) => d.port === state.chosen);
    if (!dev) return;
    const useMpy = state.form.fmt === "mpy" && state.mpy;
    const payload = useMpy ? state.mpy : new TextEncoder().encode(state.slim);
    const vid = parseHex(state.form.vid, DEFAULT_VID);
    const pid = parseHex(state.form.pid, DEFAULT_PID);
    const name = state.form.name.replace(/[^\x20-\x7e]/g, "").slice(0, 9) || "myapp";

    state.log = [];
    setPhase("flashing");
    logLine(`flashing ${payload.length} bytes (${useMpy ? "app.mpy" : "app.py"}) to port ${dev.port}…`);

    try {
      const script = buildFlashScript({
        port: dev.port,
        name,
        vid,
        pid,
        fname: useMpy ? "app.mpy" : "app.py",
        payload,
      });
      let failed = null;
      const stages = {
        detect: "EEPROM answered",
        compile: "code compiles on the badge",
        header: "hexpansion header written + verified",
        format: "littlefs formatted",
        write: "app written + read back byte-for-byte",
      };
      const parse = jsonLineParser((ev) => {
        if (ev.ok === false) {
          failed = ev;
          logLine(`✗ ${ev.stage}: ${ev.error}`, "err");
        } else if (ev.stage === "done") {
          logLine("✓ done");
        } else if (stages[ev.stage]) {
          let extra = "";
          if (ev.stage === "format") extra = ` (${ev.free} bytes free)`;
          if (ev.stage === "write") extra = ` (${ev.bytes} bytes)`;
          logLine(`✓ ${stages[ev.stage]}${extra}`);
        }
      });
      const dec = new TextDecoder();
      await state.client.exec(script, {
        timeoutMs: 60000,
        onStdout: (bytes) => parse(dec.decode(bytes, { stream: true })),
      });
      if (failed) {
        setPhase("flashfail");
        return;
      }
      logLine("rebooting the badge…");
      render();
      await cleanup({ reboot: true });
      setPhase("done");
    } catch (err) {
      fail(err);
    }
  }

  function fail(err) {
    state.error = err?.traceback || err?.message || String(err);
    cleanup({ reboot: true });
    setPhase("error");
  }

  // --- payload preparation ---------------------------------------------------------

  async function preparePayloads() {
    state.code = getCode();
    state.slim = slimPython(state.code);
    state.mpy = null;
    state.mpyError = null;
    try {
      state.mpy = await compileMpy(state.code);
    } catch (err) {
      state.mpyError = err.message;
    }
    if (state.phase === "pick") render();
  }

  // --- rendering --------------------------------------------------------------------

  function bar(n) {
    const pct = Math.min(100, Math.round((n / EEPROM_BUDGET) * 100));
    const cls = n > EEPROM_BUDGET ? "over" : pct > 85 ? "warn" : "";
    return `<div class="flash-bar ${cls}"><div style="width:${pct}%"></div></div>`;
  }

  function render() {
    const { phase } = state;
    let html = `<header><strong>⚡ flash to a hexpansion</strong>
      <button class="tbtn" data-act="close" title="close">✕</button></header>`;

    if (phase === "pickport" || phase === "idle") {
      html += `<div class="flash-body">
        <p>Writes the current program to a <a href="https://github.com/codemyriad/protogon"
        target="_blank" rel="noreferrer">Protogon</a> (or any writable hexpansion EEPROM)
        plugged into your badge, so it runs whenever the hexpansion is inserted.</p>
        <ol>
          <li>plug the badge into USB${mock ? " (mock badge in use)" : ""}</li>
          <li>close anything else using its serial port (mpremote, a terminal)</li>
          <li>the Protogon's P1 jumper must be <strong>open</strong> (open = writable)</li>
          <li>badge firmware <strong>v1.12.0 or newer</strong> (older can't read the
            EEPROM and wedges the slot on insert — Settings → System Update)</li>
        </ol>
        ${serialSupported() || mock
          ? `<button class="tbtn flash-primary" data-act="connect">connect the badge</button>
             <label class="flash-anydev"><input type="checkbox" id="flash-anydev">
             show all serial devices (badge not listed?)</label>`
          : `<p class="flash-err">This browser has no WebSerial — flashing needs
             Chrome or Edge on a computer. (Everything else here works fine.)</p>`}
      </div>`;
    } else if (phase === "connecting" || phase === "scanning") {
      html += `<div class="flash-body"><p class="flash-busy">
        ${phase === "connecting" ? "waiting for the port…" : "talking to the badge…"}</p>
        ${renderLog()}</div>`;
    } else if (phase === "pick") {
      html += renderPick();
    } else if (phase === "flashing") {
      html += `<div class="flash-body"><p class="flash-busy">flashing — don't unplug…</p>
        ${renderLog()}</div>`;
    } else if (phase === "flashfail") {
      html += `<div class="flash-body">${renderLog()}
        <p class="flash-err">The flash did not complete. If the header would not stick,
        the P1 jumper is probably shorted (shorted = write-protected) — open it and retry.</p>
        <p>The badge has been rebooted.</p>
        <button class="tbtn flash-primary" data-act="connect">try again</button></div>`;
    } else if (phase === "done") {
      html += `<div class="flash-body">${renderLog()}
        <p class="flash-ok">✓ Flashed. The badge is rebooting — the hexpansion will mount
        and your app takes the screen. Short P1 afterwards to write-protect it.</p>
        <button class="tbtn flash-primary" data-act="connect">flash another</button>
        <button class="tbtn" data-act="close">done</button></div>`;
    } else if (phase === "error") {
      html += `<div class="flash-body">
        <p class="flash-err">${esc(state.error)}</p>
        <p>The badge was rebooted (if it was reachable). Unplug/replug usually clears
        a wedged port.</p>
        <button class="tbtn flash-primary" data-act="connect">try again</button></div>`;
    }

    dialog.innerHTML = html;
    wire();
  }

  function renderLog() {
    return `<pre class="flash-log">${state.log
      .map((l) => `<span class="${l.cls}">${esc(l.text)}</span>`)
      .join("\n")}</pre>`;
  }

  function renderPick() {
    const pyBytes = new TextEncoder().encode(state.slim).length;
    const devs = state.devices;
    const flashable = devs.filter((d) => d.writable && d.alen === 2);
    if (state.chosen == null || !flashable.some((d) => d.port === state.chosen)) {
      state.chosen = flashable[0]?.port ?? null;
    }

    let list;
    if (!devs.length) {
      list = `<p class="flash-err">No hexpansion EEPROMs found on any port. Is the
        Protogon seated? (Ports are 1–6, clockwise from the top-right slot.)</p>`;
    } else {
      list = `<div class="flash-ports">${devs
        .map((d) => {
          const ok = d.writable && d.alen === 2;
          const label = d.name
            ? `“${esc(d.name)}” <span class="dim">(${hex4(d.vid)}:${hex4(d.pid)})</span>`
            : `blank EEPROM`;
          const why = !d.writable
            ? "write-protected — P1 jumper shorted?"
            : d.alen !== 2
              ? "small 1-byte-address EEPROM — not a Protogon"
              : d.name
                ? "will be overwritten"
                : "ready";
          return `<label class="flash-port ${ok ? "" : "off"}">
            <input type="radio" name="flash-port" value="${d.port}"
              ${ok ? "" : "disabled"} ${state.chosen === d.port ? "checked" : ""}>
            <span><strong>port ${d.port}</strong> · ${label}
            <em class="${ok ? "dim" : "err"}">${why}</em></span></label>`;
        })
        .join("")}</div>`;
    }

    const mpyLabel = state.mpy
      ? `app.mpy — compiled bytecode, ${state.mpy.length} bytes ${bar(state.mpy.length)}`
      : state.mpyError
        ? `app.mpy — <span class="err">compile failed</span>`
        : `app.mpy — compiling…`;

    // .mpy can only be chosen once it has compiled; fall back otherwise.
    if (state.form.fmt === "mpy" && !state.mpy) state.form.fmt = "py";
    const useMpy = state.form.fmt === "mpy" && state.mpy;
    const overBudget = (useMpy ? state.mpy.length : pyBytes) > EEPROM_BUDGET;

    const fwv = parseVersion(state.firmware);
    const fwWarn =
      fwv && versionBelow(fwv, MIN_FIRMWARE)
        ? `<p class="flash-err">⚠ badge firmware ${esc(state.firmware)} predates the
           EEPROM fix (v1.12.0). It cannot mount the hexpansion and may have wedged
           the slot on insert. Update via Settings → System Update, then reseat the
           Protogon. Flashing may still succeed but the badge won't run it until updated.</p>`
        : "";

    return `<div class="flash-body">
      ${fwWarn}
      ${list}
      <div class="flash-opts">
        <label>name on the badge
          <input id="flash-name" maxlength="9" value="${esc(state.form.name)}" spellcheck="false">
        </label>
        <fieldset>
          <legend>format</legend>
          <label><input type="radio" name="flash-fmt" id="flash-fmt-py"
            ${state.form.fmt === "py" ? "checked" : ""}>
            app.py — source, comments stripped, ${pyBytes} bytes ${bar(pyBytes)}</label>
          <label><input type="radio" name="flash-fmt" id="flash-fmt-mpy"
            ${state.mpy ? "" : "disabled"} ${useMpy ? "checked" : ""}> ${mpyLabel}</label>
          <p class="dim flash-note">.mpy is ~half the size but tied to the firmware's
          bytecode format — after a major firmware update, reflash. .py keeps working.</p>
          ${state.mpyError ? `<pre class="flash-log err">${esc(state.mpyError)}</pre>` : ""}
        </fieldset>
        <details class="flash-adv"><summary>advanced (vid/pid)</summary>
          <p class="dim flash-note">All playground apps share one “personal experiment”
          id (0xCAFE:0x7063) — the badge shows the name above, not the id, so they
          don't collide. Only change this if you're building a real, registered
          hexpansion (<a href="https://github.com/emfcamp/hexpansion-firmwares"
          target="_blank" rel="noreferrer">registry</a>).</p>
          <label>vid <input id="flash-vid" value="${esc(state.form.vid)}" size="6"></label>
          <label>pid <input id="flash-pid" value="${esc(state.form.pid)}" size="6"></label>
        </details>
      </div>
      <button class="tbtn flash-primary" data-act="flash"
        ${state.chosen == null || overBudget ? "disabled" : ""}>
        flash port ${state.chosen ?? "—"}</button>
      ${overBudget ? `<span class="err">too big for the ~${(EEPROM_BUDGET / 1024).toFixed(1)} KB EEPROM budget</span>` : ""}
      <button class="tbtn" data-act="rescan">rescan</button>
    </div>`;
  }

  function wire() {
    dialog.querySelector('[data-act="close"]')?.addEventListener("click", () => dialog.close());
    dialog.querySelector('[data-act="connect"]')?.addEventListener("click", async () => {
      await cleanup({ reboot: false }); // "flash another": fresh session
      connectAndScan($("#flash-anydev")?.checked);
    });
    dialog.querySelector('[data-act="flash"]')?.addEventListener("click", flash);
    dialog.querySelector('[data-act="rescan"]')?.addEventListener("click", async () => {
      await cleanup({ reboot: true });
      connectAndScan(false);
    });
    for (const radio of dialog.querySelectorAll('input[name="flash-port"]')) {
      radio.addEventListener("change", () => {
        state.chosen = Number(radio.value);
        render();
      });
    }
    for (const radio of dialog.querySelectorAll('input[name="flash-fmt"]')) {
      radio.addEventListener("change", () => {
        if (radio.checked) state.form.fmt = radio.id === "flash-fmt-mpy" ? "mpy" : "py";
        render(); // refresh the size bar + over-budget gate
      });
    }
    // Text inputs write straight to state on the way in; do NOT re-render (it
    // would rebuild the input and drop the caret).
    const nameEl = dialog.querySelector("#flash-name");
    nameEl?.addEventListener("input", () => (state.form.name = nameEl.value));
    const vidEl = dialog.querySelector("#flash-vid");
    vidEl?.addEventListener("input", () => (state.form.vid = vidEl.value));
    const pidEl = dialog.querySelector("#flash-pid");
    pidEl?.addEventListener("input", () => (state.form.pid = pidEl.value));
  }

  // --- entry ----------------------------------------------------------------------

  $("#btn-flash").addEventListener("click", () => {
    state.phase = "pickport";
    state.log = [];
    state.form = { name: appName(), fmt: "py", vid: hex4(DEFAULT_VID), pid: hex4(DEFAULT_PID) };
    preparePayloads();
    render();
    dialog.showModal();
  });

  dialog.addEventListener("close", () => {
    cleanup({ reboot: true });
    setPhaseSafe("idle");
  });

  function setPhaseSafe(p) {
    state.phase = p; // no render: the dialog is closed
  }

  return {
    // QA hooks
    state,
    open: () => $("#btn-flash").click(),
  };
}

function parseHex(text, fallback) {
  const n = parseInt(String(text).replace(/^0x/i, ""), 16);
  return Number.isInteger(n) && n >= 0 && n <= 0xffff ? n : fallback;
}

const hex4 = (n) => "0x" + n.toString(16).toUpperCase().padStart(4, "0");
