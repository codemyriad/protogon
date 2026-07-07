// app.js — the page: editor on the left, a live badge on the right.
//
// The badge (Pyodide + real firmware scheduler + ctx.wasm) runs in a Worker;
// this file owns everything the user touches: the CodeMirror pane, the demo
// gallery, badge chrome (LED glows, button hotspots, pointer-tilt IMU), the
// pause/step/speed transport, and the watchdog that reboots the worker if an
// edit ever wedges Python (the editor itself can never freeze).

import {
  createEditor,
  showRuntimeError,
  clearRuntimeError,
  replaceDoc,
} from "./editor.js";
import { initLibrary } from "./library.js";
import { initFlash } from "./flash.js";
import { initFloat } from "./float.js";
import * as previews from "./previews.js";

const $ = (sel) => document.querySelector(sel);
const narrow = () => matchMedia("(max-width: 900px)").matches;

// --- badge geometry (fractions of the 733x733 sim badge photo) -------------
const LED_POS = [
  [443, 90], [573, 163], [646, 293], [646, 440], [573, 566], [443, 640],
  [296, 640], [173, 566], [93, 440], [93, 293], [173, 163], [296, 90],
];
// Physical buttons A..F, clockwise from top. Bit order matches boot.py.
const BUTTONS = [
  { pos: [370, 33], label: "A", key: "ArrowUp", hint: "up" },
  { pos: [670, 190], label: "B", key: "ArrowRight", hint: "right" },
  { pos: [670, 540], label: "C", key: "Enter", hint: "confirm" },
  { pos: [370, 710], label: "D", key: "ArrowDown", hint: "down" },
  { pos: [75, 540], label: "E", key: "ArrowLeft", hint: "left" },
  { pos: [85, 190], label: "F", key: "Escape", hint: "cancel" },
];

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let worker = null;
let workerReady = false;
let lastPong = 0;
let lastGoodSrc = null; // last source the badge accepted
let buttonBits = 0;
let paused = false;
let library = null;
let editor = null;
let bootedOnce = false;
let swapSeq = 0;
const swapSrcById = new Map(); // in-flight swap id -> source we sent
const reviveIds = new Set(); // swaps we initiated to revive after a crash
let lastAutoRevive = 0;
let currentSpeed = 1;
let pongPending = false;
let lastPingAt = 0;
let isStale = false;
let captureTimer = null;
let pregenStarted = false;

// ---------------------------------------------------------------------------
// Badge chrome
// ---------------------------------------------------------------------------
function pct(v) {
  return `${((v / 733) * 100).toFixed(2)}%`;
}

function buildBadge() {
  const badge = $("#badge");

  for (const [x, y] of LED_POS) {
    const el = document.createElement("div");
    el.className = "led";
    el.style.left = pct(x);
    el.style.top = pct(y);
    badge.appendChild(el);
  }

  for (let i = 0; i < BUTTONS.length; i++) {
    const b = BUTTONS[i];
    const el = document.createElement("div");
    el.className = "btn-hotspot";
    el.style.left = pct(b.pos[0]);
    el.style.top = pct(b.pos[1]);
    el.title = `${b.label} · ${b.hint} (${b.key})`;
    el.innerHTML = `<span>${b.label}</span>`;
    el.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      el.setPointerCapture(ev.pointerId);
      setButton(i, true);
    });
    const release = () => setButton(i, false);
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);
    badge.appendChild(el);
    b.el = el;
  }

  // Pointer tilt = IMU. Hover moves a virtual bubble level toward the pointer.
  let rafPending = false;
  badge.addEventListener("pointermove", (ev) => {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const r = badge.getBoundingClientRect();
      const nx = ((ev.clientX - r.left) / r.width - 0.5) * 2; // -1..1
      const ny = ((ev.clientY - r.top) / r.height - 0.5) * 2;
      // Tilt "toward" the pointer, in m/s^2 (badge apps expect ~±4.9 ≈ 30°).
      send({ type: "acc", x: nx * 4.9, y: ny * 4.9 });
    });
  });
  badge.addEventListener("pointerleave", () => send({ type: "acc", x: 0, y: 0 }));
}

function setButton(i, down) {
  const bit = 1 << i;
  const next = down ? buttonBits | bit : buttonBits & ~bit;
  if (next === buttonBits) return;
  buttonBits = next;
  BUTTONS[i].el?.classList.toggle("held", down);
  send({ type: "buttons", bits: buttonBits });
}

function bindKeyboard() {
  const keyIndex = new Map(BUTTONS.map((b, i) => [b.key, i]));
  const shouldIgnore = (ev) =>
    $("#editor").contains(ev.target) ||
    (ev.target instanceof Element &&
      ev.target.closest("button, input, select, textarea, a, summary, dialog"));
  window.addEventListener("keydown", (ev) => {
    // Esc dismisses the browse flyout (like every other overlay here) instead
    // of reaching the badge as its CANCEL button and minimising the app.
    // Dialogs keep their native Esc handling.
    if (
      ev.key === "Escape" &&
      !$("#flyout").hidden &&
      !(ev.target instanceof Element && ev.target.closest("dialog"))
    ) {
      setFlyout(false);
      return;
    }
    if (shouldIgnore(ev) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const i = keyIndex.get(ev.key);
    if (i === undefined) return;
    ev.preventDefault();
    setButton(i, true);
  });
  window.addEventListener("keyup", (ev) => {
    const i = keyIndex.get(ev.key);
    if (i === undefined) return;
    setButton(i, false);
  });
  window.addEventListener("blur", () => {
    for (let i = 0; i < 6; i++) setButton(i, false);
  });
}

function renderLeds(colors) {
  // colors: 19 entries, ring = indices 1..12 (matches tildagonos.leds[1..12])
  const els = document.querySelectorAll("#badge .led");
  for (let i = 0; i < 12; i++) {
    const c = colors[i + 1] || [0, 0, 0];
    const [r, g, b] = c.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255));
    const el = els[i];
    if (r || g || b) {
      el.style.background = `rgb(${r},${g},${b})`;
      el.style.boxShadow = `0 0 14px 5px rgba(${r},${g},${b},0.55)`;
    } else {
      el.style.background = "rgba(255,255,255,0.06)";
      el.style.boxShadow = "none";
    }
  }
}

// ---------------------------------------------------------------------------
// Worker lifecycle
// ---------------------------------------------------------------------------
function send(msg) {
  worker?.postMessage(msg);
}

function requestSwap(src, { revive = false } = {}) {
  const id = ++swapSeq;
  swapSrcById.set(id, src);
  if (revive) reviveIds.add(id);
  send({ type: "swap", src, id });
}

function bootStatus(text, isError = false) {
  const el = $("#screen-boot");
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.toggle("error", isError);
}

function spawnWorker(src) {
  workerReady = false;
  pongPending = false;
  if (worker) {
    worker.onmessage = null; // a dead worker's queued messages must not land
    worker.terminate();
  }
  swapSrcById.clear();
  reviveIds.clear();
  clearTimeout(captureTimer); // don't snapshot a badge that is mid-reboot

  // transferControlToOffscreen is once-per-element: rebuild the canvas node.
  const old = $("#screen");
  const canvas = old.cloneNode(false);
  old.replaceWith(canvas);

  const BUILD = typeof __BUILD_ID__ === "string" ? __BUILD_ID__ : "dev";
  worker = new Worker(new URL(`./sim-worker.js?b=${BUILD}`, import.meta.url), {
    type: "module",
  });
  worker.onmessage = (ev) => onWorkerMessage(ev.data);

  const offscreen = canvas.transferControlToOffscreen();
  worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
  bootStatus(bootedOnce ? "rebooting badge…" : "booting badge…");

  if (src) requestSwap(src);
  if (paused) send({ type: "clock", paused: true });
  if (currentSpeed !== 1) send({ type: "clock", speed: currentSpeed });
}

function onWorkerMessage(msg) {
  switch (msg.type) {
    case "progress":
      bootStatus(msg.stage + "…");
      break;
    case "ready":
      workerReady = true;
      bootedOnce = true;
      lastPong = performance.now();
      bootStatus("");
      // Once the visible badge is comfortably up, fill in gallery thumbnails
      // that have never been captured (throwaway background worker).
      if (!pregenStarted) {
        pregenStarted = true;
        setTimeout(async () => {
          if (!library) return;
          previews.startPregen(await library.getPregenItems());
        }, 8000);
      }
      break;
    case "swapped": {
      const sent = swapSrcById.get(msg.id);
      const wasRevive = reviveIds.delete(msg.id);
      swapSrcById.delete(msg.id);
      if (msg.ok && sent !== undefined) {
        lastGoodSrc = sent;
        // A revive re-runs code that just crashed: keep the pinned error so
        // the user can still see why. Editor swaps clear it if the badge now
        // runs exactly what's on screen.
        if (!wasRevive && sent === editor.state.doc.toString()) {
          clearRuntimeError(editor);
          setStale(false);
          // Thumbnail: snapshot the screen once the app has ~3 s of life in
          // it. The key/hash ride along and come back with the frame, so a
          // capture that outlives a script switch can't be filed under the
          // wrong card (the worker answers in message order; by receipt time
          // a mismatched tag or a stale badge means "drop it").
          scheduleCapture(sent);
        } else if (!wasRevive) {
          setStale(true);
        }
      } else if (!msg.ok) {
        setStale(true);
      }
      break;
    }
    case "captured": {
      if (!msg.bitmap) break;
      const url = previews.encodeBitmap(msg.bitmap);
      previews.setNow(url); // the dock tile mirrors whatever is running
      const tag = msg.id;
      if (tag?.key && !isStale && library && tag.key === library.currentKey()) {
        if (library.wantsCapture(tag)) {
          previews.record(tag.key, tag.hash, url);
        } else {
          // A demo back at its shipped source: the bundled preview is the
          // truth again, so retire any cached draft-era capture.
          previews.dropPreview(tag.key);
        }
      }
      break;
    }
    case "apperror": {
      const line = msg.line ?? 1;
      showRuntimeError(editor, line, msg.message);
      setStale(true);
      if (msg.kind === "crash") {
        logConsole(`✗ ${msg.message}`, "err");
        // A delayed crash stopped the running app: revive the last good code
        // so the badge never stays frozen. Rate-limited in case the "good"
        // code itself has a delayed bug.
        if (lastGoodSrc && Date.now() - lastAutoRevive > 3000) {
          lastAutoRevive = Date.now();
          requestSwap(lastGoodSrc, { revive: true });
        }
      }
      break;
    }
    case "leds":
      renderLeds(msg.colors);
      break;
    case "stats":
      $("#stat-fps").textContent = `${msg.fps} fps`;
      $("#stat-t").textContent = `t ${msg.tSec.toFixed(1)}s`;
      break;
    case "print":
      logConsole(msg.text, msg.stream);
      break;
    case "pong":
      lastPong = performance.now();
      pongPending = false;
      break;
    case "fatal":
      bootStatus("badge failed to boot — see console panel", true);
      logConsole(msg.message, "err");
      break;
  }
}

function startWatchdog() {
  // Reboot only when a ping actually went unanswered. Judging by "time since
  // last pong" would false-positive in hidden tabs, where browsers throttle
  // this interval to once a minute but the worker still answers instantly.
  setInterval(() => {
    if (!workerReady) return;
    if (pongPending) {
      if (performance.now() - lastPingAt > 4000) {
        pongPending = false;
        logConsole("⟳ badge stopped responding (infinite loop?) — rebooting", "err");
        // Reboot with the last ACCEPTED code, not the wedged editor text.
        if (lastGoodSrc && editor.state.doc.toString() !== lastGoodSrc) {
          setStale(true);
        }
        spawnWorker(lastGoodSrc);
      }
      return;
    }
    pongPending = true;
    lastPingAt = performance.now();
    send({ type: "ping", id: lastPingAt });
  }, 1000);
}

function scheduleCapture(src) {
  clearTimeout(captureTimer);
  const tag = { key: library?.currentKey(), hash: previews.hashSrc(src) };
  if (!tag.key) return;
  captureTimer = setTimeout(() => send({ type: "capture", id: tag }), 3000);
}

function setStale(stale) {
  isStale = stale;
  $("#stale-dot").hidden = !stale;
  const dot = $("#run-dot");
  dot.classList.toggle("stale", stale);
  dot.title = stale
    ? "the badge is running the last working code, not this edit"
    : "the badge is running this code";
}

// ---------------------------------------------------------------------------
// Console panel
// ---------------------------------------------------------------------------
function logConsole(text, stream) {
  const pre = $("#console-log");
  for (const line of String(text).split("\n")) {
    if (!line.trim()) continue;
    const span = document.createElement("span");
    span.className = stream === "err" ? "c-err" : "c-out";
    span.textContent = line + "\n";
    pre.appendChild(span);
  }
  while (pre.childNodes.length > 300) pre.removeChild(pre.firstChild);
  pre.scrollTop = pre.scrollHeight;
}

// ---------------------------------------------------------------------------
// Transport (pause / step / reset / speed)
// ---------------------------------------------------------------------------
function bindTransport() {
  const pauseBtn = $("#btn-pause");
  pauseBtn.addEventListener("click", () => {
    paused = !paused;
    pauseBtn.textContent = paused ? "▶" : "❚❚";
    pauseBtn.title = paused ? "resume badge time" : "pause badge time";
    send({ type: "clock", paused });
    $("#btn-step").disabled = !paused;
  });
  $("#btn-step").addEventListener("click", () => send({ type: "step", ms: 50 }));
  $("#btn-reset").addEventListener("click", () => {
    send({ type: "reset" });
  });
  const speed = $("#speed");
  // The design's slider has a lime fill up to the knob; a plain range input
  // only tints the thumb, so paint the track with a two-stop gradient.
  const paintSpeed = () => {
    const min = parseFloat(speed.min);
    const max = parseFloat(speed.max);
    const pct = ((parseFloat(speed.value) - min) / (max - min)) * 100;
    speed.style.background =
      `linear-gradient(to right, var(--accent) 0 ${pct}%, #2a2a2a ${pct}% 100%)`;
  };
  paintSpeed();
  speed.addEventListener("input", () => {
    paintSpeed();
    const s = Math.pow(10, parseFloat(speed.value));
    currentSpeed = s;
    $("#speed-label").textContent = `${s.toFixed(s < 1 ? 2 : 1)}×`;
    send({ type: "clock", speed: s });
  });
}

// ---------------------------------------------------------------------------
// Chrome: browse flyout, info window, "new" buttons
// ---------------------------------------------------------------------------
const FLYOUT_KEY = "tlp.ui.flyout.v1";

function setFlyout(open, { persist = true } = {}) {
  $("#flyout").hidden = !open;
  document.body.classList.toggle("flyout-open", open);
  $("#btn-browse").setAttribute("aria-expanded", String(open));
  // Only explicit toggles (▤ / ✕ / Esc) are remembered as a preference;
  // the auto-close after picking a card shouldn't flip the next visit's
  // default.
  if (!persist) return;
  try {
    localStorage.setItem(FLYOUT_KEY, open ? "1" : "0");
  } catch {}
}

function flyoutIsOpen() {
  return !$("#flyout").hidden;
}

function bindChrome({ newSnippet }) {
  // Browse flyout: an overlay over the editor. Defaults open on desktop so
  // the gallery is discoverable, closed on phones where it covers everything.
  let open;
  try {
    const saved = localStorage.getItem(FLYOUT_KEY);
    open = saved === null ? !narrow() : saved === "1";
  } catch {
    open = !narrow();
  }
  setFlyout(open);
  $("#btn-browse").addEventListener("click", () => setFlyout(!flyoutIsOpen()));
  $("#btn-flyout-close").addEventListener("click", () => setFlyout(false));

  // Info window: both ? buttons open it; ✕, backdrop click, or Esc close it.
  const info = $("#info-dialog");
  const openInfo = () => info.showModal();
  $("#btn-info-top").addEventListener("click", openInfo);
  $("#btn-info-dock").addEventListener("click", openInfo);
  $("#btn-info-close").addEventListener("click", () => info.close());
  info.addEventListener("click", (ev) => {
    if (ev.target === info) info.close(); // backdrop
  });

  for (const id of ["#btn-new-top", "#btn-new-dock", "#btn-new-flyout"]) {
    $(id).addEventListener("click", newSnippet);
  }
}

// ---------------------------------------------------------------------------
// Wire-up
// ---------------------------------------------------------------------------
async function main() {
  buildBadge();
  bindKeyboard();
  bindTransport();
  const float = initFloat();
  previews.registerNow($("#now-thumb"));
  bindChrome({ newSnippet: () => library?.switchTo({ kind: "new" }) });

  editor = createEditor({
    parent: $("#editor"),
    doc: "",
    onChange: (src) => {
      library?.onCodeChanged(src);
      if (!src.trim()) return;
      requestSwap(src);
    },
  });

  spawnWorker();
  startWatchdog();

  // Assigned after initLibrary returns; the flyout's ⚡ quick actions can fire
  // before then and guard on it.
  let flash = null;

  // The gallery + snippet library owns the flyout cards, the toolbar and the
  // hash.
  library = await initLibrary({
    setCode: (src) => replaceDoc(editor, src),
    getCode: () => editor.state.doc.toString(),
    onTitle: (name) => {
      document.title = `${name} · Tildagon live playground`;
    },
    // Picking a card loads it AND puts the gallery away, so the code and
    // badge are immediately front and centre (the dock strip covers quick
    // switching from there).
    onPicked: () => setFlyout(false, { persist: false }),
    onFlashRequest: async (ref) => {
      // Cards are clickable while the first demo is still loading; until
      // library/flash exist there is nothing to flash yet.
      if (!library || !flash) return;
      await library.switchTo(ref);
      setFlyout(false, { persist: false });
      flash.open();
    },
  });

  flash = initFlash({
    getCode: () => editor.state.doc.toString(),
    getName: () => library.currentName(),
  });

  // Long-running scripts keep evolving visually: refresh the running
  // script's thumbnail (and the dock tile) every so often.
  setInterval(() => {
    if (!workerReady || paused || isStale || !library) return;
    if (document.visibilityState !== "visible") return;
    const key = library.currentKey();
    if (!key) return;
    send({
      type: "capture",
      id: { key, hash: previews.hashSrc(editor.state.doc.toString()) },
    });
  }, 10000);

  // Small hook for headless QA (and console tinkerers).
  window.playground = {
    editor,
    send,
    library,
    flash,
    float,
    previews,
    setCode: (src) => replaceDoc(editor, src),
    getCode: () => editor.state.doc.toString(),
    isReady: () => workerReady,
    lastGood: () => lastGoodSrc,
    setFlyout,
  };
}

main();
