// library.js — the gallery and your snippets: the browse-flyout cards, the
// name/save toolbar, hash routing, and the never-lose-work draft flow.
//
// What's on screen is always one of:
//   demo     read-only source shipped with the site (#tixy). Editing forks:
//            "save" makes a snippet; the demo itself never changes.
//   snippet  yours, in localStorage (#s/<id>). Save overwrites, fork copies.
//   new      a fresh template (#new). Saving creates the snippet.
//   shared   code carried entirely in the URL (#gz/<deflate+base64url>).
//
// Every debounced edit is autosaved as a draft keyed by what's being edited,
// so closing the tab mid-edit loses nothing: coming back to that demo or
// snippet restores the draft (with a "restored unsaved edits" note and a
// revert button).
//
// The flyout lists every demo and every snippet as a card: captured-frame
// thumbnail (previews.js), name, "size · date" meta, and flash / duplicate /
// delete quick actions. A search box filters both sections by name.

import * as store from "./store.js";
import * as previews from "./previews.js";

const $ = (sel) => document.querySelector(sel);

// Bust caches that ignore no-store for the demo sources too (pgs.sh and other
// CDNs cache them for a week; the page's own entry points are already
// ?b=-versioned, but these runtime fetches weren't).
const BUILD = typeof __BUILD_ID__ === "string" ? __BUILD_ID__ : "dev";

// The starting point for a brand-new snippet: small, alive, and built to be
// pulled apart — every number scrubs, both colours get swatches.
const NEW_TEMPLATE = `# untitled -- a dot on a string. Make it yours.
#
# BUTTONS   CANCEL exits (on a real badge)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
BG     = (0.05, 0.05, 0.10)   # background colour
INK    = (1.0, 0.75, 0.2)     # dot colour
SPEED  = 1.0                  # how fast time flows for this app
SWING  = 80                   # how far the dot swings, px (screen is 240x240)
SIZE   = 12.0                 # dot radius


class Mine(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += (delta / 1000.0) * SPEED
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.minimise()
            return False
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(BG[0], BG[1], BG[2]).rectangle(-120, -120, 240, 240).fill()
        x = math.sin(self.t) * SWING
        y = math.cos(self.t * 1.3) * SWING
        ctx.rgb(INK[0], INK[1], INK[2])
        ctx.arc(x, y, SIZE, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Mine

# ------------------------------ try this --------------------------------------
# - drag the 1.3 in draw(): 1.0 is a circle, 2.0 a figure-eight, 1.618...?
# - make it a comet: draw several dots at self.t - i * 0.05, smaller each time
`;

// A short stable hash so two different share links get two different draft
// keys (a constant "shared" key would show link A's edits when you open B).
function hash32(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

const refKey = (ref) =>
  ref.kind === "demo" ? `demo:${ref.id}`
  : ref.kind === "snippet" ? `snip:${ref.id}`
  : ref.kind === "shared" ? `shared:${hash32(ref.data)}`
  : "new";

const refHash = (ref) =>
  ref.kind === "demo" ? `#${ref.id}`
  : ref.kind === "snippet" ? `#s/${ref.id}`
  : ref.kind === "shared" ? `#gz/${ref.data}`
  : "#new";

function parseHash(hash, manifest) {
  const h = hash.replace(/^#/, "");
  if (!h) return null;
  if (h === "new") return { kind: "new" };
  if (h.startsWith("s/")) return { kind: "snippet", id: h.slice(2) };
  if (h.startsWith("gz/")) return { kind: "shared", data: h.slice(3) };
  if (manifest.some((d) => d.id === h)) return { kind: "demo", id: h };
  return null;
}

// Walk one line of Python and return the triple-quote state at its end, given
// the state at its start (null, or the active `"""`/`'''` delimiter). Enough
// of a tokenizer to know when a line is "inside a docstring": it tracks
// single- and triple-quoted strings and stops at a `#` that starts a comment,
// so a `#` inside a string is never mistaken for a comment and a `"""` inside
// a comment never opens a string.
// Index just past the closing `delim` at or after `from`, honouring `\`
// escapes, or -1 if the delimiter doesn't close on this line.
function closeTripleAt(line, from, delim) {
  let i = from;
  while (i < line.length) {
    if (line[i] === "\\") {
      i += 2;
      continue;
    }
    if (line.slice(i, i + 3) === delim) return i + 3;
    i++;
  }
  return -1;
}

function scanTriple(line, triple) {
  let i = 0;
  if (triple) {
    const end = closeTripleAt(line, 0, triple);
    if (end < 0) return triple; // still open at end of line
    i = end;
    triple = null;
  }
  let quote = null; // active single-line string delimiter
  while (i < line.length) {
    const c = line[i];
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
      i++;
      continue;
    }
    if (c === "#") return null; // rest of the line is a comment
    if ((c === '"' || c === "'") && line.slice(i, i + 3) === c + c + c) {
      const t = c + c + c;
      const end = closeTripleAt(line, i + 3, t);
      if (end < 0) return t; // opens a docstring that runs past this line
      i = end;
      continue;
    }
    if (c === '"' || c === "'") quote = c;
    i++;
  }
  return null;
}

// Strip full-line comments and blank runs before flashing (they waste EEPROM),
// like slim() in the badge-side flasher — but correctly skip lines inside a
// triple-quoted docstring, where a leading "#" is data, not a comment.
export function slimPython(src) {
  const out = [];
  let blank = false;
  let triple = null;
  for (const line of src.split("\n")) {
    if (triple === null && line.trim().startsWith("#")) continue;
    const wasInString = triple !== null;
    triple = scanTriple(line, triple);
    const s = line.trim();
    if (!s && !wasInString) {
      if (blank) continue;
      blank = true;
    } else {
      blank = false;
    }
    out.push(line.replace(/\s+$/, ""));
  }
  return out.join("\n").replace(/^\n+/, "") + "\n";
}

const utf8len = (s) => new TextEncoder().encode(s).length;

// ~6.5 KB: 15 x 512-byte littlefs blocks minus the superblock pair, minus
// metadata — measured on real provisioning runs. The flash dialog re-checks
// the true number on the badge before writing.
export const EEPROM_BUDGET = 6500;

const slimKb = (src) => `${(utf8len(slimPython(src)) / 1024).toFixed(1)} KB`;

// Card meta dates read like the design: "today", "yesterday", "3d ago",
// then "May 20" (with the year once it isn't this one).
function relDate(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const now = new Date();
  const mid = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((mid(now) - mid(d)) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  const opts = { month: "short", day: "numeric" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString("en", opts);
}

// ---------------------------------------------------------------------------

export async function initLibrary({ setCode, getCode, onTitle, onPicked, onFlashRequest }) {
  const res = await fetch(`demos/demos.json?b=${BUILD}`);
  if (!res.ok) throw new Error(`${res.status} loading demos.json`);
  const manifest = await res.json();

  const state = {
    ref: null, // what the buffer belongs to
    baseline: "", // last saved / shipped source for that ref
    dirty: false,
    manifest,
  };

  // Demo sources, fetched once up front: cards need sizes, duplicate needs
  // code, switching becomes instant, and the preview pre-generator needs
  // something to run. ~50 KB total, same-origin, cached.
  const srcCache = new Map();
  const prefetchDone = Promise.allSettled(
    manifest.map((d) =>
      fetch(`demos/${d.id}.py?b=${BUILD}`)
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`${r.status}`))))
        .then((text) => srcCache.set(d.id, text))
    )
  );

  // --- toolbar elements ------------------------------------------------------
  const nameInput = $("#snip-name");
  const saveBtn = $("#btn-save");
  const revertBtn = $("#btn-revert");
  const sizeBadge = $("#size-badge");
  const msgEl = $("#toolbar-msg");
  const menuFork = $("#menu-fork");
  const menuDelete = $("#menu-delete");

  let msgTimer = null;
  function toast(text) {
    msgEl.textContent = text;
    msgEl.classList.add("show");
    clearTimeout(msgTimer);
    msgTimer = setTimeout(() => msgEl.classList.remove("show"), 2600);
  }

  function currentName() {
    if (state.ref.kind === "demo") {
      return manifest.find((d) => d.id === state.ref.id)?.title || state.ref.id;
    }
    return nameInput.value.trim() || "untitled";
  }

  function updateToolbar() {
    const { ref, dirty } = state;
    const isDemo = ref.kind === "demo";
    const isSnippet = ref.kind === "snippet";
    // A pending rename counts as unsaved too, so the dirty dot / revert nudge
    // you to save it (a rename isn't in the autosaved draft).
    const renamed = isSnippet && currentName() !== getSnippetName();
    const unsaved = dirty || renamed;
    nameInput.readOnly = isDemo;
    nameInput.classList.toggle("as-label", isDemo);
    $("#dirty-dot").hidden = !unsaved;
    revertBtn.hidden = !unsaved;
    saveBtn.textContent = isSnippet ? "save" : "save as snippet";
    saveBtn.title = isSnippet
      ? "overwrite this snippet (Ctrl+S)"
      : isDemo
        ? "the demo stays as shipped; saving makes your own copy (Ctrl+S)"
        : "keep this as a snippet (Ctrl+S)";
    saveBtn.disabled = isSnippet && !unsaved;
    menuDelete.hidden = !isSnippet;
    updateSize(getCode());
  }

  function getSnippetName() {
    return state.ref.kind === "snippet"
      ? store.getSnippet(state.ref.id)?.name
      : null;
  }

  function updateSize(src) {
    const slim = utf8len(slimPython(src));
    sizeBadge.textContent = `${(slim / 1024).toFixed(1)} KB`;
    const over = slim > EEPROM_BUDGET;
    const warn = !over && slim > EEPROM_BUDGET * 0.85;
    sizeBadge.classList.toggle("over", over);
    sizeBadge.classList.toggle("warn", warn);
    sizeBadge.title =
      `${slim} bytes after comments are stripped (as flashed to a hexpansion` +
      ` EEPROM; ~${EEPROM_BUDGET} fit). Raw: ${utf8len(src)} bytes.` +
      (over ? " TOO BIG to flash — trim it." : "");
  }

  // --- gallery cards -----------------------------------------------------------
  let searchQuery = "";

  function makeAction(cls, glyph, title, onClick) {
    const b = document.createElement("button");
    b.className = cls;
    b.textContent = glyph;
    b.title = title;
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onClick();
    });
    return b;
  }

  function makeCard({ ref, name, meta, title, deletable }) {
    const key = refKey(ref);
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.key = key;
    card.dataset.search = `${name} ${title || ""}`.toLowerCase();
    if (title) card.title = title;

    const thumb = document.createElement("div");
    thumb.className = "thumb";
    previews.bindThumb(thumb, key);

    const text = document.createElement("div");
    text.className = "card-text";
    const nameEl = document.createElement("div");
    nameEl.className = "card-name";
    nameEl.textContent = name;
    const metaEl = document.createElement("div");
    metaEl.className = "card-meta";
    metaEl.textContent = meta;
    text.append(nameEl, metaEl);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    actions.append(
      makeAction("card-flash", "⚡", `flash “${name}” to a hexpansion`, () =>
        onFlashRequest(ref)
      ),
      makeAction("card-dup", "⧉", `duplicate “${name}” as a new snippet`, () =>
        duplicateCard(ref)
      )
    );
    if (deletable) {
      actions.append(
        makeAction("card-del", "✕", `delete “${name}”`, () => deleteCard(ref))
      );
    }

    card.append(thumb, text, actions);
    // The old chips were <button>s; keep the gallery keyboard-reachable.
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `open ${name}`);
    const pick = () => {
      switchTo(ref);
      onPicked?.();
    };
    card.addEventListener("click", pick);
    card.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (ev.target !== card) return; // let the quick-action buttons be buttons
      ev.preventDefault();
      pick();
    });
    return card;
  }

  function buildDemoCards() {
    const box = $("#demo-cards");
    box.textContent = "";
    for (const demo of manifest) {
      const src = srcCache.get(demo.id);
      box.appendChild(
        makeCard({
          ref: { kind: "demo", id: demo.id },
          name: demo.title,
          meta: src ? slimKb(src) : "…",
          title: demo.blurb || demo.id,
          deletable: false,
        })
      );
    }
    $("#demos-count").textContent = manifest.length;
    markActiveCard();
    applyFilter();
  }

  function buildMineCards() {
    const box = $("#mine-cards");
    box.textContent = "";
    const snippets = store.listSnippets();
    for (const s of snippets) {
      box.appendChild(
        makeCard({
          ref: { kind: "snippet", id: s.id },
          name: s.name,
          meta: `${slimKb(s.code)} · ${relDate(s.updatedAt || s.createdAt)}`,
          title: s.basedOn ? `based on ${s.basedOn}` : "your snippet",
          deletable: true,
        })
      );
    }
    $("#mine-head").hidden = !snippets.length;
    $("#mine-count").textContent = snippets.length;
    buildDockTiles(); // snippets changed -> the dock strip did too
    markActiveCard();
    applyFilter();
  }

  // The dock's collapsed-gallery strip: a mini thumbnail per script, title on
  // hover, click to open — quick switching without the flyout.
  function makeDockTile(ref, name) {
    const tile = document.createElement("button");
    tile.className = "dock-tile thumb";
    tile.dataset.key = refKey(ref);
    tile.title = name;
    tile.setAttribute("aria-label", `open ${name}`);
    previews.bindThumb(tile, refKey(ref));
    tile.addEventListener("click", () => switchTo(ref));
    return tile;
  }

  function buildDockTiles() {
    const box = $("#dock-tiles");
    box.textContent = "";
    for (const demo of manifest) {
      box.appendChild(makeDockTile({ kind: "demo", id: demo.id }, demo.title));
    }
    const snippets = store.listSnippets();
    if (snippets.length) {
      const rule = document.createElement("div");
      rule.className = "dock-tiles-rule";
      box.appendChild(rule);
      for (const s of snippets) {
        box.appendChild(makeDockTile({ kind: "snippet", id: s.id }, s.name));
      }
    }
    markActiveCard();
  }

  function markActiveCard() {
    const key = state.ref ? refKey(state.ref) : "";
    for (const el of document.querySelectorAll(".card, .dock-tile")) {
      el.classList.toggle("active", el.dataset.key === key);
    }
  }

  function applyFilter() {
    const q = searchQuery.trim().toLowerCase();
    let demosShown = 0;
    let mineShown = 0;
    for (const card of document.querySelectorAll("#demo-cards .card")) {
      const hit = !q || card.dataset.search.includes(q);
      card.hidden = !hit;
      if (hit) demosShown++;
    }
    for (const card of document.querySelectorAll("#mine-cards .card")) {
      const hit = !q || card.dataset.search.includes(q);
      card.hidden = !hit;
      if (hit) mineShown++;
    }
    $("#demos-head").hidden = Boolean(q) && !demosShown;
    $("#mine-head").hidden = (Boolean(q) && !mineShown) || !store.listSnippets().length;
  }

  $("#gallery-search").addEventListener("input", (ev) => {
    searchQuery = ev.target.value;
    applyFilter();
  });

  // --- card quick actions ---------------------------------------------------------
  function baselineOf(ref) {
    if (ref.kind === "demo") return srcCache.get(ref.id) ?? null;
    if (ref.kind === "snippet") return store.getSnippet(ref.id)?.code ?? null;
    return null;
  }

  async function duplicateCard(ref) {
    let code = baselineOf(ref);
    if (code == null && ref.kind === "demo") {
      // Prefetch missed (flaky network): fetch on demand instead of a dead end.
      try {
        code = await resolveBaseline(ref); // populates srcCache
        buildDemoCards(); // un-stick the "…" meta
      } catch {
        return toast("could not load that demo — check the connection");
      }
    }
    if (code == null) return toast("could not load that source");
    const isDemo = ref.kind === "demo";
    const baseName = isDemo
      ? manifest.find((d) => d.id === ref.id)?.title || ref.id
      : store.getSnippet(ref.id)?.name || "snippet";
    const snip = store.saveSnippet({
      name: store.uniqueName(`${baseName} copy`),
      code,
      basedOn: isDemo ? ref.id : store.getSnippet(ref.id)?.basedOn || null,
    });
    previews.copyPreview(refKey(ref), `snip:${snip.id}`);
    buildMineCards();
    switchTo({ kind: "snippet", id: snip.id });
    toast(`copied to “${snip.name}” — it's yours now`);
  }

  function deleteCard(ref) {
    if (ref.kind !== "snippet") return;
    if (state.ref?.kind === "snippet" && state.ref.id === ref.id) return remove();
    const snip = store.getSnippet(ref.id);
    if (!confirm(`Delete “${snip?.name}”? There is no undo.`)) return;
    store.deleteSnippet(ref.id);
    store.clearDraft(refKey(ref));
    previews.dropPreview(refKey(ref));
    buildMineCards();
    toast("deleted");
  }

  // --- switching --------------------------------------------------------------
  let switchSeq = 0;

  async function resolveBaseline(ref) {
    switch (ref.kind) {
      case "demo": {
        if (srcCache.has(ref.id)) return srcCache.get(ref.id);
        const r = await fetch(`demos/${ref.id}.py?b=${BUILD}`);
        if (!r.ok) throw new Error(`${r.status} loading demo ${ref.id}`);
        const text = await r.text();
        srcCache.set(ref.id, text);
        return text;
      }
      case "snippet": {
        const snip = store.getSnippet(ref.id);
        if (!snip) throw new Error("snippet not found");
        return snip.code;
      }
      case "shared":
        return await store.decodeShare(ref.data);
      default:
        return NEW_TEMPLATE;
    }
  }

  async function switchTo(ref) {
    const token = ++switchSeq;
    let baseline;
    try {
      baseline = await resolveBaseline(ref);
    } catch (err) {
      console.warn(err);
      toast(
        ref.kind === "shared" ? "could not decode that share link" : `${err.message}`
      );
      if (state.ref) return; // stay where we are
      ref = { kind: "demo", id: manifest[0].id };
      baseline = await resolveBaseline(ref);
    }
    if (token !== switchSeq) return; // a newer switch overtook this one

    state.ref = ref;
    state.baseline = baseline;

    const draft = store.getDraft(refKey(ref));
    const restored = draft !== null && draft !== baseline;
    state.dirty = restored;
    if (draft !== null && !restored) store.clearDraft(refKey(ref));

    if (ref.kind === "demo") {
      nameInput.value = manifest.find((d) => d.id === ref.id)?.title || ref.id;
    } else if (ref.kind === "snippet") {
      nameInput.value = store.getSnippet(ref.id).name;
    } else if (ref.kind === "shared") {
      nameInput.value = "shared code";
    } else {
      nameInput.value = "untitled";
    }

    if (location.hash !== refHash(ref)) {
      suppressHash = refHash(ref);
      location.hash = refHash(ref);
    }

    setCode(restored ? draft : baseline);
    previews.setNowFromKey(refKey(ref));
    markActiveCard();
    updateToolbar();
    onTitle(currentName());
    if (restored) toast("restored unsaved edits — revert to discard");
  }

  // --- saving -------------------------------------------------------------------
  function save() {
    const code = getCode();
    const { ref } = state;
    if (ref.kind === "snippet") {
      const snip = store.saveSnippet({ id: ref.id, name: currentName(), code });
      state.baseline = code;
      state.dirty = false;
      store.clearDraft(refKey(ref));
      buildMineCards();
      updateToolbar();
      onTitle(snip.name);
      toast("saved");
      return;
    }
    // demo / new / shared: create a snippet from the buffer
    const demoTitle =
      ref.kind === "demo"
        ? manifest.find((d) => d.id === ref.id)?.title || ref.id
        : null;
    const base = demoTitle ? `${demoTitle} remix` : currentName();
    const snip = store.saveSnippet({
      name: store.uniqueName(base),
      code,
      basedOn: ref.kind === "demo" ? ref.id : null,
    });
    previews.copyPreview(refKey(ref), `snip:${snip.id}`);
    store.clearDraft(refKey(ref));
    state.ref = { kind: "snippet", id: snip.id };
    state.baseline = code;
    state.dirty = false;
    nameInput.value = snip.name;
    suppressHash = refHash(state.ref);
    location.hash = refHash(state.ref);
    buildMineCards();
    updateToolbar();
    onTitle(snip.name);
    toast(`saved as “${snip.name}” — it's yours now`);
  }

  function fork() {
    const code = getCode();
    const fromKey = refKey(state.ref);
    const snip = store.saveSnippet({
      name: store.uniqueName(`${currentName()} copy`),
      code,
      basedOn: state.ref.kind === "snippet"
        ? store.getSnippet(state.ref.id)?.basedOn || null
        : state.ref.kind === "demo" ? state.ref.id : null,
    });
    previews.copyPreview(fromKey, `snip:${snip.id}`);
    state.ref = { kind: "snippet", id: snip.id };
    state.baseline = code;
    state.dirty = false;
    nameInput.value = snip.name;
    suppressHash = refHash(state.ref);
    location.hash = refHash(state.ref);
    buildMineCards();
    updateToolbar();
    onTitle(snip.name);
    toast(`copied to “${snip.name}”`);
  }

  function remove() {
    if (state.ref.kind !== "snippet") return;
    const snip = store.getSnippet(state.ref.id);
    if (!confirm(`Delete “${snip?.name}”? There is no undo.`)) return;
    store.deleteSnippet(state.ref.id);
    store.clearDraft(refKey(state.ref));
    previews.dropPreview(refKey(state.ref));
    buildMineCards();
    const back = snip?.basedOn && manifest.some((d) => d.id === snip.basedOn)
      ? snip.basedOn
      : manifest[0].id;
    switchTo({ kind: "demo", id: back });
    toast("deleted");
  }

  function revert() {
    store.clearDraft(refKey(state.ref));
    state.dirty = false;
    if (state.ref.kind === "snippet") nameInput.value = getSnippetName(); // undo a rename too
    setCode(state.baseline);
    updateToolbar();
    toast("back to the saved version");
  }

  // --- menu actions ---------------------------------------------------------------
  const menu = $("#lib-menu");
  const closeMenu = () => menu.removeAttribute("open");
  document.addEventListener("pointerdown", (ev) => {
    if (menu.hasAttribute("open") && !menu.contains(ev.target)) closeMenu();
  });
  // The dropdown is position:fixed (the toolbar is an overflow-x scroll
  // container that would clip an absolute child) — anchor it on open.
  menu.addEventListener("toggle", () => {
    if (!menu.open) return;
    const r = menu.querySelector("summary").getBoundingClientRect();
    const items = menu.querySelector(".menu-items");
    items.style.top = `${r.bottom + 4}px`;
    items.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
  });

  function slug(name) {
    return (
      name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") ||
      "snippet"
    );
  }

  function download(filename, text, type = "text/x-python") {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  $("#menu-download").addEventListener("click", () => {
    closeMenu();
    download(`${slug(currentName())}.py`, getCode());
  });

  $("#menu-share").addEventListener("click", async () => {
    closeMenu();
    const data = await store.encodeShare(getCode());
    const url = `${location.origin}${location.pathname}#gz/${data}`;
    try {
      await navigator.clipboard.writeText(url);
      toast(`share link copied (${url.length} chars) — the code IS the link`);
    } catch {
      prompt("copy this share link:", url);
    }
  });

  menuFork.addEventListener("click", () => {
    closeMenu();
    fork();
  });

  menuDelete.addEventListener("click", () => {
    closeMenu();
    remove();
  });

  $("#menu-export").addEventListener("click", () => {
    closeMenu();
    const n = store.listSnippets().length;
    if (!n) return toast("no snippets to back up yet");
    download(
      `tildagon-snippets-${new Date().toISOString().slice(0, 10)}.json`,
      store.exportAll(),
      "application/json"
    );
    toast(`backed up ${n} snippet${n === 1 ? "" : "s"}`);
  });

  $("#menu-import").addEventListener("click", () => {
    closeMenu();
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const { added, skipped } = store.importAll(await file.text());
        buildMineCards();
        toast(`imported ${added} snippet${added === 1 ? "" : "s"}` +
              (skipped ? ` (${skipped} already here)` : ""));
      } catch (err) {
        toast(`import failed: ${err.message}`);
      }
    });
    input.click();
  });

  // --- wiring ------------------------------------------------------------------
  saveBtn.addEventListener("click", save);
  revertBtn.addEventListener("click", revert);

  nameInput.addEventListener("input", () => updateToolbar());
  nameInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      nameInput.blur();
      if (state.ref.kind === "snippet") save();
    }
  });

  window.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key === "s") {
      ev.preventDefault();
      save();
    }
  });

  let suppressHash = null;
  window.addEventListener("hashchange", () => {
    if (location.hash === suppressHash) {
      suppressHash = null;
      return;
    }
    const ref = parseHash(location.hash, manifest);
    if (ref && refKey(ref) !== refKey(state.ref ?? { kind: "new" })) switchTo(ref);
    else if (ref && ref.kind === "shared") switchTo(ref); // new payload, same kind
  });

  if (!store.storageIsPersistent()) {
    toast("heads-up: localStorage is unavailable — snippets won't survive this tab");
  }

  buildDemoCards();
  buildMineCards();
  await switchTo(
    parseHash(location.hash, manifest) || { kind: "demo", id: manifest[0].id }
  );
  // Demo sizes (and duplicate/pregen sources) arrive shortly after first
  // paint; rebuild the demo cards once they're in.
  prefetchDone.then(() => buildDemoCards());

  return {
    // editor change hook: dirty tracking + draft autosave + size badge
    onCodeChanged(src) {
      if (!state.ref) return;
      const dirty = src !== state.baseline;
      if (dirty !== state.dirty) {
        state.dirty = dirty;
        updateToolbar();
      } else {
        updateSize(src);
      }
      if (dirty) store.setDraft(refKey(state.ref), src);
      else store.clearDraft(refKey(state.ref));
    },
    currentName,
    currentKey: () => (state.ref ? refKey(state.ref) : null),
    switchTo,
    save,
    // What the preview pre-generator should run: every demo and snippet, as
    // the editor would open it (draft over baseline), keyed + content-hashed.
    async getPregenItems() {
      await prefetchDone;
      const items = [];
      for (const d of manifest) {
        const key = `demo:${d.id}`;
        const src = store.getDraft(key) ?? srcCache.get(d.id);
        if (src) items.push({ key, src, hash: previews.hashSrc(src) });
      }
      for (const s of store.listSnippets()) {
        const key = `snip:${s.id}`;
        const src = store.getDraft(key) ?? s.code;
        items.push({ key, src, hash: previews.hashSrc(src) });
      }
      return items;
    },
    state, // for QA
  };
}
