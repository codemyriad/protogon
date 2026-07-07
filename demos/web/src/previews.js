// previews.js — thumbnails for every script, shown as the round badge screen.
//
// Two sources, by ownership:
//   bundled demos   ship with the site: build.sh copies each committed
//                   demos/<name>/preview.png (an emulator-captured frame) to
//                   dist/demos/<id>.png, so the gallery is fully illustrated
//                   on first paint with zero work in the browser.
//   user scripts    (snippets, drafts, edited demos) are captured live: the
//                   badge screen ~3 s after the script starts (app.js
//                   schedules it; the worker answers a "capture" message with
//                   an ImageBitmap), cached in localStorage keyed by ref
//                   ("snip:<id>", "demo:tixy") + a hash of the source, so an
//                   edit regenerates and an untouched script never re-renders.
//                   Snippets that never ran this side of a content change are
//                   filled in by a throwaway second sim worker (desktop only,
//                   terminated on first sign of a wedged VM).
//
// Display is uniform: a cached user capture wins, else a demo falls back to
// its bundled image, else the skeleton tile. The CSS paints the image as a
// circle (the screen disc is the inscribed circle of the square framebuffer).

const KEY = "tlp.previews.v1";
const MAX_PREVIEWS = 60; // prune LRU past this — data URLs add up
const THUMB = 160; // stored square px: covers the 66x42 card at 2x

const BUILD = typeof __BUILD_ID__ === "string" ? __BUILD_ID__ : "dev";

// Same djb2 as library.js's share-draft keys; previews only need "did the
// source change", not cryptographic strength.
export function hashSrc(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// --- store -------------------------------------------------------------------

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

const mem = load(); // { key: {hash, url, at} } — user scripts only
let persistTimer = null;

function persistSoon() {
  // Captures can arrive every few seconds while a demo runs; batch the
  // (whole-map) localStorage writes instead of rewriting per frame.
  if (persistTimer) return;
  persistTimer = setTimeout(persistNow, 15000);
}

function persistNow() {
  clearTimeout(persistTimer);
  persistTimer = null;
  try {
    localStorage.setItem(KEY, JSON.stringify(mem));
  } catch {
    /* quota/private mode: previews stay in-memory for this tab */
  }
}

// Flush pending captures before the tab goes away.
addEventListener("pagehide", () => persistTimer && persistNow());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && persistTimer) persistNow();
});

function prune() {
  const keys = Object.keys(mem);
  if (keys.length <= MAX_PREVIEWS) return;
  keys
    .sort((a, b) => (mem[a].at || 0) - (mem[b].at || 0))
    .slice(0, keys.length - MAX_PREVIEWS)
    .forEach((k) => delete mem[k]);
}

export const getUrl = (key) => mem[key]?.url || null;
export const hasFresh = (key, hash) => mem[key]?.hash === hash;

// A demo's shipped thumbnail (dist/demos/<id>.png, from build.sh).
const bundledUrl = (key) =>
  key.startsWith("demo:") ? `demos/${key.slice(5)}.png?b=${BUILD}` : null;

const urlFor = (key) => getUrl(key) || bundledUrl(key);

// --- encoding ------------------------------------------------------------------

const scratch = document.createElement("canvas");
scratch.width = scratch.height = THUMB;

// ImageBitmap -> small data URL. Closes the bitmap.
export function encodeBitmap(bitmap) {
  const ctx = scratch.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, THUMB, THUMB);
  bitmap.close();
  let url = scratch.toDataURL("image/webp", 0.8);
  if (!url.startsWith("data:image/webp")) url = scratch.toDataURL("image/jpeg", 0.85);
  return url;
}

// --- DOM binding -----------------------------------------------------------------
// Thumbnail elements register with a key; every record() repaints the ones
// showing that key. The dock "NOW" tile is separate: it always mirrors the
// latest capture, whatever script it belongs to. The image lands in the
// --preview custom property; .thumb's CSS draws it as the round screen.

let nowEl = null;

function paint(el, url) {
  el.classList.toggle("has-preview", !!url);
  if (url) el.style.setProperty("--preview", `url("${url}")`);
  else el.style.removeProperty("--preview");
}

export function bindThumb(el, key) {
  el.dataset.previewKey = key;
  paint(el, urlFor(key));
}

export function registerNow(el) {
  nowEl = el;
}

export function setNow(url) {
  if (nowEl && url) paint(nowEl, url);
}

// Seed the NOW tile from a key's cached/bundled art (used on script switch, so
// the dock doesn't keep showing the previous script for the first 3 s).
export function setNowFromKey(key) {
  if (nowEl) paint(nowEl, urlFor(key)); // nothing known -> skeleton, honestly "loading"
}

function repaintKey(key) {
  const url = urlFor(key);
  for (const el of document.querySelectorAll("[data-preview-key]")) {
    if (el.dataset.previewKey === key) paint(el, url);
  }
}

// --- recording ---------------------------------------------------------------------

export function record(key, hash, url) {
  mem[key] = { hash, url, at: Date.now() };
  prune();
  persistSoon();
  repaintKey(key);
}

export function copyPreview(fromKey, toKey) {
  const p = mem[fromKey];
  if (p) record(toKey, p.hash, p.url);
  else if (bundledUrl(fromKey)) record(toKey, "", bundledUrl(fromKey));
}

export function dropPreview(key) {
  if (!(key in mem)) return;
  delete mem[key];
  persistSoon();
  repaintKey(key); // demos fall back to their bundled image
}

// --- the throwaway capture worker ------------------------------------------------
// One extra sim worker (its own Pyodide boot, ~16 MB), fed a queue
// sequentially, terminated when done — or on the FIRST timeout: a script with
// a busy loop starves the worker's event loop forever, and feeding more items
// to a pegged core helps nobody.

const PREGEN_SPEED = 4;
const PREGEN_SETTLE_MS = 850; // real ms; x4 ≈ 3.4 s of badge time
const ITEM_TIMEOUT = 15000;
const BOOT_TIMEOUT = 90000;

let captureWorkerBusy = false;

// items: [{src, ...}] — onFrame(item, bitmap) per successful capture;
// skip(item) checked just before each run. Resolves when the queue is done
// or the worker was declared dead.
async function runCaptureQueue(items, { speed, settleMs, skip = () => false, onFrame }) {
  if (captureWorkerBusy || !items.length) return;
  captureWorkerBusy = true;

  const worker = new Worker(new URL(`./sim-worker.js?b=${BUILD}`, import.meta.url), {
    type: "module",
  });
  let waiter = null; // {type, id, resolve} — one outstanding wait at a time
  let fatal = false;

  worker.onmessage = (ev) => {
    const msg = ev.data;
    if (msg.type === "fatal") fatal = true;
    if (!waiter || msg.type !== waiter.type) return;
    if (waiter.id !== null && msg.id !== waiter.id) return;
    const w = waiter;
    waiter = null;
    w.resolve(msg);
  };

  const waitFor = (type, id = null) =>
    new Promise((resolve) => {
      waiter = { type, id, resolve };
    });
  const withTimeout = (promise, ms) =>
    Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))]);

  try {
    const canvas = new OffscreenCanvas(240, 240);
    worker.postMessage({ type: "init", canvas }, [canvas]);
    if (!(await withTimeout(waitFor("ready"), BOOT_TIMEOUT))) return;
    worker.postMessage({ type: "clock", speed });

    let swapSeq = 0;
    for (const item of items) {
      if (fatal || skip(item)) continue;
      const id = ++swapSeq;
      worker.postMessage({ type: "swap", src: item.src, id, carry: false });
      const swapped = await withTimeout(waitFor("swapped", id), ITEM_TIMEOUT);
      if (!swapped) return; // wedged VM — kill it, don't feed it
      if (!swapped.ok) continue; // just a broken script; the VM is fine
      await new Promise((r) => setTimeout(r, settleMs));
      worker.postMessage({ type: "capture" });
      const captured = await withTimeout(waitFor("captured"), ITEM_TIMEOUT);
      if (!captured) return;
      if (captured.bitmap) onFrame(item, captured.bitmap);
    }
  } finally {
    worker.terminate();
    captureWorkerBusy = false;
  }
}

// --- background pre-generation (user scripts only) ---------------------------------
// items: [{key, hash, src}] — anything already captured at this hash is
// skipped; bundled demos never come through here (library.getPregenItems
// sends snippets and draft-edited demos only).

export function startPregen(items) {
  if (matchMedia("(max-width: 900px)").matches) return; // phones: skip the 2nd VM
  if ((navigator.hardwareConcurrency || 2) < 4) return;
  const asOf = Date.now(); // never clobber a live capture recorded after this
  const queue = items.filter((it) => it.src && !hasFresh(it.key, it.hash));
  runCaptureQueue(queue, {
    speed: PREGEN_SPEED,
    settleMs: PREGEN_SETTLE_MS,
    skip: (it) => hasFresh(it.key, it.hash) || mem[it.key]?.at > asOf,
    onFrame: (it, bitmap) => {
      if (mem[it.key]?.at > asOf) return bitmap.close(); // live capture won the race
      record(it.key, it.hash, encodeBitmap(bitmap));
    },
  }).catch(() => {});
}

// --- maintainer tooling ---------------------------------------------------------
// Renders every bundled demo at TRUE speed and full screen resolution and
// returns {id: PNG dataURL} — the source of the committed
// demos/<name>/preview.png files (see demos/web/README.md to regenerate).
// Console: await playground.previews.renderPreviewPack(playground.library.demoSources())

export async function renderPreviewPack(items, { size = 240, settleMs = 3000 } = {}) {
  const out = {};
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  await runCaptureQueue(items, {
    speed: 1,
    settleMs,
    onFrame: (item, bitmap) => {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size, size);
      ctx.drawImage(bitmap, 0, 0, size, size);
      bitmap.close();
      out[item.id] = canvas.toDataURL("image/png");
    },
  });
  return out;
}
