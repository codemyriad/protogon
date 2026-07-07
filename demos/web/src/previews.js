// previews.js — captured badge-screen thumbnails for every script.
//
// Each gallery card (and the dock "NOW" tile) shows a real frame of that
// script running in the emulator: the badge screen is captured ~3 seconds
// after a script starts (app.js schedules it; the worker answers a "capture"
// message with an ImageBitmap of its OffscreenCanvas). Captures are cached in
// localStorage keyed by ref ("demo:tixy", "snip:<id>") together with a hash
// of the source that produced them, so an edited script regenerates its
// thumbnail and an untouched one never re-renders.
//
// Scripts that have never run this side of a content change would show a
// skeleton tile forever, so a throwaway second worker (same sim-worker.js,
// its own Pyodide) quietly runs each missing script at 4x badge time and
// captures it — desktop only, one at a time, terminated when the queue is
// done. The visible badge never flickers.

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

const mem = load(); // { key: {hash, url, at} }
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
// latest capture, whatever script it belongs to.

let nowEl = null;

function paint(el, url) {
  el.classList.toggle("has-preview", !!url);
  el.style.backgroundImage = url ? `url("${url}")` : "";
}

export function bindThumb(el, key) {
  el.dataset.previewKey = key;
  paint(el, getUrl(key));
}

export function registerNow(el) {
  nowEl = el;
}

export function setNow(url) {
  if (nowEl && url) paint(nowEl, url);
}

// Seed the NOW tile from a key's cached capture (used on script switch, so
// the dock doesn't keep showing the previous script for the first 3 s).
export function setNowFromKey(key) {
  const url = getUrl(key);
  if (nowEl) paint(nowEl, url); // no capture yet -> skeleton, honestly "loading"
}

function repaintKey(key) {
  const url = getUrl(key);
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
}

export function dropPreview(key) {
  if (!(key in mem)) return;
  delete mem[key];
  persistSoon();
}

// --- background pre-generation --------------------------------------------------------
// items: [{key, hash, src}] — anything already captured at this hash is
// skipped. Spawns ONE extra sim worker (its own Pyodide boot, ~16 MB — hence
// the desktop gate), runs the queue sequentially at 4x badge time, captures
// each script ~3.4 s (badge time) in, and terminates itself.

const PREGEN_SPEED = 4;
const PREGEN_SETTLE_MS = 850; // real ms; x4 ≈ 3.4 s of badge time
const PREGEN_ITEM_TIMEOUT = 15000;
const PREGEN_BOOT_TIMEOUT = 90000;

let pregenRunning = false;

export function startPregen(items) {
  if (pregenRunning) return;
  if (matchMedia("(max-width: 900px)").matches) return; // phones: skip the 2nd VM
  if ((navigator.hardwareConcurrency || 2) < 4) return;
  const queue = items.filter((it) => it.src && !hasFresh(it.key, it.hash));
  if (!queue.length) return;
  pregenRunning = true;

  const worker = new Worker(new URL(`./sim-worker.js?b=${BUILD}`, import.meta.url), {
    type: "module",
  });
  let swapSeq = 0;
  let waiter = null; // {type, id, resolve} — one outstanding wait at a time
  let timer = null;

  const finish = () => {
    clearTimeout(timer);
    worker.terminate();
    pregenRunning = false;
  };

  const waitFor = (type, id = null) =>
    new Promise((resolve) => {
      waiter = { type, id, resolve };
    });

  worker.onmessage = (ev) => {
    const msg = ev.data;
    if (msg.type === "fatal") return finish();
    if (!waiter || msg.type !== waiter.type) return;
    if (waiter.id !== null && msg.id !== waiter.id) return;
    const w = waiter;
    waiter = null;
    w.resolve(msg);
  };

  const withTimeout = (promise, ms) =>
    Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))]);

  const asOf = Date.now(); // never clobber a live capture recorded after this

  (async () => {
    const canvas = new OffscreenCanvas(240, 240);
    worker.postMessage({ type: "init", canvas }, [canvas]);
    if (!(await withTimeout(waitFor("ready"), PREGEN_BOOT_TIMEOUT))) return finish();
    worker.postMessage({ type: "clock", speed: PREGEN_SPEED });

    for (const item of queue) {
      if (hasFresh(item.key, item.hash)) continue; // the live badge got there first
      if (mem[item.key]?.at > asOf) continue; // ...or captured something newer
      const id = ++swapSeq;
      worker.postMessage({ type: "swap", src: item.src, id, carry: false });
      const swapped = await withTimeout(waitFor("swapped", id), PREGEN_ITEM_TIMEOUT);
      // A timeout means the VM is wedged (a script with a busy loop starves
      // the worker's event loop forever) — kill it rather than feed the rest
      // of the queue to a pegged core. Missing thumbnails can wait.
      if (!swapped) return finish();
      if (!swapped.ok) continue; // just a broken script; the VM is fine
      await new Promise((r) => setTimeout(r, PREGEN_SETTLE_MS));
      worker.postMessage({ type: "capture" });
      const captured = await withTimeout(waitFor("captured"), PREGEN_ITEM_TIMEOUT);
      if (!captured) return finish();
      if (!captured.bitmap) continue;
      if (mem[item.key]?.at > asOf) continue; // live capture won the race
      record(item.key, item.hash, encodeBitmap(captured.bitmap));
    }
    finish();
  })().catch(finish);
}
