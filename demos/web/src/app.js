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

const $ = (sel) => document.querySelector(sel);

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
let manifest = [];
let currentDemo = null;
let editor = null;
let bootedOnce = false;
let swapSeq = 0;
const swapSrcById = new Map(); // in-flight swap id -> source we sent
let lastAutoRevive = 0;

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
  const inEditor = (ev) => $("#editor").contains(ev.target);
  window.addEventListener("keydown", (ev) => {
    if (inEditor(ev) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
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

function requestSwap(src) {
  const id = ++swapSeq;
  swapSrcById.set(id, src);
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
  worker?.terminate();

  // transferControlToOffscreen is once-per-element: rebuild the canvas node.
  const old = $("#screen");
  const canvas = old.cloneNode(false);
  old.replaceWith(canvas);

  worker = new Worker(new URL("./sim-worker.js", import.meta.url), {
    type: "module",
  });
  worker.onmessage = (ev) => onWorkerMessage(ev.data);

  const offscreen = canvas.transferControlToOffscreen();
  worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
  bootStatus(bootedOnce ? "rebooting badge…" : "booting badge…");

  if (src) requestSwap(src);
  if (paused) send({ type: "clock", paused: true });
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
      break;
    case "swapped": {
      const sent = swapSrcById.get(msg.id);
      swapSrcById.delete(msg.id);
      if (msg.ok && sent !== undefined) {
        lastGoodSrc = sent;
        // Only clear the error state if the badge now runs what's on screen.
        if (sent === editor.state.doc.toString()) {
          clearRuntimeError(editor);
          setStale(false);
        } else {
          setStale(true);
        }
      } else if (!msg.ok) {
        setStale(true);
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
          requestSwap(lastGoodSrc);
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
      break;
    case "fatal":
      bootStatus("badge failed to boot — see console panel", true);
      logConsole(msg.message, "err");
      break;
  }
}

function startWatchdog() {
  setInterval(() => {
    if (!workerReady) return;
    send({ type: "ping", id: Date.now() });
    if (performance.now() - lastPong > 4000) {
      logConsole("⟳ badge stopped responding (infinite loop?) — rebooting", "err");
      // Reboot with the last ACCEPTED code, not the wedged editor text.
      if (lastGoodSrc && editor.state.doc.toString() !== lastGoodSrc) {
        setStale(true);
      }
      spawnWorker(lastGoodSrc);
    }
  }, 1000);
}

function setStale(stale) {
  $("#stale-dot").hidden = !stale;
}

// ---------------------------------------------------------------------------
// Console panel
// ---------------------------------------------------------------------------
const consoleLines = [];
function logConsole(text, stream) {
  for (const line of String(text).split("\n")) {
    if (!line.trim()) continue;
    consoleLines.push({ line, stream });
  }
  while (consoleLines.length > 300) consoleLines.shift();
  const pre = $("#console-log");
  pre.innerHTML = consoleLines
    .map(
      (l) =>
        `<span class="${l.stream === "err" ? "c-err" : "c-out"}">${escapeHtml(l.line)}</span>`
    )
    .join("\n");
  pre.scrollTop = pre.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
}

// ---------------------------------------------------------------------------
// Transport (pause / step / reset / speed)
// ---------------------------------------------------------------------------
function bindTransport() {
  const pauseBtn = $("#btn-pause");
  pauseBtn.addEventListener("click", () => {
    paused = !paused;
    pauseBtn.textContent = paused ? "▶" : "⏸";
    pauseBtn.title = paused ? "resume badge time" : "pause badge time";
    send({ type: "clock", paused });
    $("#btn-step").disabled = !paused;
  });
  $("#btn-step").addEventListener("click", () => send({ type: "step", ms: 50 }));
  $("#btn-reset").addEventListener("click", () => {
    send({ type: "reset" });
  });
  const speed = $("#speed");
  speed.addEventListener("input", () => {
    const s = Math.pow(10, parseFloat(speed.value));
    $("#speed-label").textContent = `${s.toFixed(s < 1 ? 2 : 1)}×`;
    send({ type: "clock", speed: s });
  });
}

// ---------------------------------------------------------------------------
// Demo gallery
// ---------------------------------------------------------------------------
async function loadManifest() {
  manifest = await (await fetch("demos/demos.json")).json();
  const nav = $("#demo-chips");
  for (const demo of manifest) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = demo.title;
    chip.title = demo.blurb || demo.id;
    chip.dataset.id = demo.id;
    chip.addEventListener("click", () => {
      if (location.hash !== `#${demo.id}`) location.hash = `#${demo.id}`;
      else switchDemo(demo.id);
    });
    nav.appendChild(chip);
  }
}

async function switchDemo(id) {
  const demo = manifest.find((d) => d.id === id) || manifest[0];
  if (!demo) return;
  currentDemo = demo.id;
  document.title = `${demo.title} · Tildagon live playground`;
  for (const chip of document.querySelectorAll(".chip")) {
    chip.classList.toggle("active", chip.dataset.id === demo.id);
  }
  const src = await (await fetch(`demos/${demo.id}.py`)).text();
  // replaceDoc triggers the editor's change listener, which swaps the app —
  // same live path as typing. Nothing to reload, ever.
  replaceDoc(editor, src);
}

// ---------------------------------------------------------------------------
// Wire-up
// ---------------------------------------------------------------------------
async function main() {
  buildBadge();
  bindKeyboard();
  bindTransport();

  editor = createEditor({
    parent: $("#editor"),
    doc: "",
    onChange: (src) => {
      if (!src.trim()) return;
      requestSwap(src);
    },
  });

  spawnWorker();
  startWatchdog();

  await loadManifest();
  const fromHash = location.hash.replace(/^#/, "");
  await switchDemo(fromHash || manifest[0]?.id);

  window.addEventListener("hashchange", () => {
    const id = location.hash.replace(/^#/, "");
    if (id && id !== currentDemo) switchDemo(id);
  });

  // Small hook for headless QA (and console tinkerers).
  window.playground = {
    editor,
    send,
    setCode: (src) => replaceDoc(editor, src),
    getCode: () => editor.state.doc.toString(),
    isReady: () => workerReady,
    lastGood: () => lastGoodSrc,
  };
}

main();
