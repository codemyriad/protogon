// library.js — the gallery and your snippets: chips, the name/save toolbar,
// hash routing, and the never-lose-work draft flow.
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

import * as store from "./store.js";

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

// ---------------------------------------------------------------------------

export async function initLibrary({ setCode, getCode, onTitle }) {
  const res = await fetch(`demos/demos.json?b=${BUILD}`);
  if (!res.ok) throw new Error(`${res.status} loading demos.json`);
  const manifest = await res.json();

  const state = {
    ref: null, // what the buffer belongs to
    baseline: "", // last saved / shipped source for that ref
    dirty: false,
    manifest,
  };

  // --- toolbar elements ------------------------------------------------------
  const nameInput = $("#snip-name");
  const saveBtn = $("#btn-save");
  const forkBtn = $("#btn-fork");
  const deleteBtn = $("#btn-delete");
  const revertBtn = $("#btn-revert");
  const sizeBadge = $("#size-badge");
  const msgEl = $("#toolbar-msg");

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
    forkBtn.hidden = !isSnippet;
    deleteBtn.hidden = !isSnippet;
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

  // --- chips -------------------------------------------------------------------
  function buildDemoChips() {
    const nav = $("#demo-chips");
    nav.textContent = "";
    for (const demo of manifest) {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = demo.title;
      chip.title = demo.blurb || demo.id;
      chip.dataset.key = `demo:${demo.id}`;
      chip.addEventListener("click", () => switchTo({ kind: "demo", id: demo.id }));
      nav.appendChild(chip);
    }
  }

  function buildSnippetChips() {
    const nav = $("#snippet-chips");
    nav.textContent = "";
    const snippets = store.listSnippets();
    if (snippets.length) {
      const label = document.createElement("span");
      label.className = "chips-label";
      label.textContent = "mine";
      nav.appendChild(label);
    }
    for (const s of snippets) {
      const chip = document.createElement("button");
      chip.className = "chip chip-mine";
      chip.textContent = s.name;
      chip.title = s.basedOn ? `based on ${s.basedOn}` : "your snippet";
      chip.dataset.key = `snip:${s.id}`;
      chip.addEventListener("click", () => switchTo({ kind: "snippet", id: s.id }));
      nav.appendChild(chip);
    }
    const plus = document.createElement("button");
    plus.className = "chip chip-new";
    plus.textContent = "+ new";
    plus.title = "start a fresh snippet";
    plus.dataset.key = "new";
    plus.addEventListener("click", () => switchTo({ kind: "new" }));
    nav.appendChild(plus);
  }

  function markActiveChip() {
    const key = refKey(state.ref);
    for (const chip of document.querySelectorAll(".chip")) {
      chip.classList.toggle("active", chip.dataset.key === key);
    }
  }

  // --- switching --------------------------------------------------------------
  let switchSeq = 0;

  async function resolveBaseline(ref) {
    switch (ref.kind) {
      case "demo": {
        const r = await fetch(`demos/${ref.id}.py?b=${BUILD}`);
        if (!r.ok) throw new Error(`${r.status} loading demo ${ref.id}`);
        return await r.text();
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
    markActiveChip();
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
      buildSnippetChips();
      markActiveChip();
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
    store.clearDraft(refKey(ref));
    state.ref = { kind: "snippet", id: snip.id };
    state.baseline = code;
    state.dirty = false;
    nameInput.value = snip.name;
    suppressHash = refHash(state.ref);
    location.hash = refHash(state.ref);
    buildSnippetChips();
    markActiveChip();
    updateToolbar();
    onTitle(snip.name);
    toast(`saved as “${snip.name}” — it's yours now`);
  }

  function fork() {
    const code = getCode();
    const snip = store.saveSnippet({
      name: store.uniqueName(`${currentName()} copy`),
      code,
      basedOn: state.ref.kind === "snippet"
        ? store.getSnippet(state.ref.id)?.basedOn || null
        : null,
    });
    state.ref = { kind: "snippet", id: snip.id };
    state.baseline = code;
    state.dirty = false;
    nameInput.value = snip.name;
    suppressHash = refHash(state.ref);
    location.hash = refHash(state.ref);
    buildSnippetChips();
    markActiveChip();
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
    buildSnippetChips();
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
        buildSnippetChips();
        markActiveChip();
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
  forkBtn.addEventListener("click", fork);
  deleteBtn.addEventListener("click", remove);
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

  buildDemoChips();
  buildSnippetChips();
  await switchTo(
    parseHash(location.hash, manifest) || { kind: "demo", id: manifest[0].id }
  );

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
    switchTo,
    save,
    state, // for QA
  };
}
