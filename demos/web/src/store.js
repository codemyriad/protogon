// store.js — where snippets live. Pure data, no DOM.
//
// Everything persists in localStorage:
//   tlp.snippets.v1   [{id, name, code, basedOn, createdAt, updatedAt}, ...]
//   tlp.drafts.v1     {refKey: {code, at}, ...}   unsaved buffers, autosaved
//
// Drafts exist so the editor NEVER loses work: every debounced edit lands
// here, keyed by what was being edited ("demo:tixy", "snip:<id>", "new").
// Saving promotes the draft into a snippet and clears it.
//
// Share links (#gz/<data>) hold the whole program in the URL: deflate-raw +
// base64url, via the browser-native CompressionStream — no library needed.
// ~5 KB of Python becomes a ~1.5 KB URL. Works on any static host.

const SNIPPETS_KEY = "tlp.snippets.v1";
const DRAFTS_KEY = "tlp.drafts.v1";
const MAX_DRAFTS = 30;

// localStorage can be unavailable (private mode, quota). Degrade to a
// same-API in-memory store and let the UI warn once. Reads still fall back to
// localStorage for keys the in-memory map never captured — otherwise a quota
// error mid-session would make already-saved snippets vanish from the UI even
// though they're safe on disk.
let storageBroken = false;
const memory = new Map();

function safeGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function readJson(key, fallback) {
  try {
    const raw = storageBroken
      ? (memory.has(key) ? memory.get(key) : safeGet(key))
      : localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  const raw = JSON.stringify(value);
  try {
    if (!storageBroken) {
      localStorage.setItem(key, raw);
      return true;
    }
  } catch {
    storageBroken = true;
  }
  memory.set(key, raw);
  return false;
}

export function storageIsPersistent() {
  if (storageBroken) return false;
  try {
    localStorage.setItem("tlp.probe", "1");
    localStorage.removeItem("tlp.probe");
    return true;
  } catch {
    storageBroken = true;
    return false;
  }
}

// --- snippets ---------------------------------------------------------------

export function listSnippets() {
  const all = readJson(SNIPPETS_KEY, []);
  return all.sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0));
}

export function getSnippet(id) {
  return listSnippets().find((s) => s.id === id) || null;
}

function newId() {
  // 122 bits of randomness so a bulk import minting many ids in one tick can't
  // collide (a Date.now()+small-random scheme would, silently sharing ids).
  if (globalThis.crypto?.randomUUID) return "s" + crypto.randomUUID();
  return (
    "s" +
    Date.now().toString(36) +
    Math.floor(Math.random() * 36 ** 6).toString(36)
  );
}

// Create (no id) or update (existing id). Returns the stored snippet.
export function saveSnippet({ id, name, code, basedOn }) {
  const all = listSnippets();
  const now = Date.now();
  let snip = id ? all.find((s) => s.id === id) : null;
  if (snip) {
    snip.name = name;
    snip.code = code;
    snip.updatedAt = now;
  } else {
    snip = {
      id: newId(),
      name,
      code,
      basedOn: basedOn || null,
      createdAt: now,
      updatedAt: now,
    };
    all.push(snip);
  }
  writeJson(SNIPPETS_KEY, all);
  return snip;
}

export function deleteSnippet(id) {
  writeJson(SNIPPETS_KEY, listSnippets().filter((s) => s.id !== id));
}

// Unique-ify "tixy remix" -> "tixy remix 2" against existing snippet names.
export function uniqueName(base) {
  const names = new Set(listSnippets().map((s) => s.name));
  if (!names.has(base)) return base;
  for (let n = 2; ; n++) {
    const candidate = `${base} ${n}`;
    if (!names.has(candidate)) return candidate;
  }
}

// --- drafts (autosaved unsaved buffers) --------------------------------------

export function getDraft(refKey) {
  const d = readJson(DRAFTS_KEY, {})[refKey];
  return d ? d.code : null;
}

export function setDraft(refKey, code) {
  const drafts = readJson(DRAFTS_KEY, {});
  drafts[refKey] = { code, at: Date.now() };
  const keys = Object.keys(drafts);
  if (keys.length > MAX_DRAFTS) {
    keys
      .sort((a, b) => drafts[a].at - drafts[b].at)
      .slice(0, keys.length - MAX_DRAFTS)
      .forEach((k) => delete drafts[k]);
  }
  writeJson(DRAFTS_KEY, drafts);
}

export function clearDraft(refKey) {
  const drafts = readJson(DRAFTS_KEY, {});
  if (refKey in drafts) {
    delete drafts[refKey];
    writeJson(DRAFTS_KEY, drafts);
  }
}

// --- backup / restore ---------------------------------------------------------

export function exportAll() {
  return JSON.stringify(
    { format: "tildagon-playground-snippets", version: 1, exportedAt: new Date().toISOString(), snippets: listSnippets() },
    null,
    1
  );
}

// Merge: same id + same code -> skip; same id + different code -> keep both
// (the imported one gets a fresh id and "(imported)" name); new id -> add.
export function importAll(jsonText) {
  const data = JSON.parse(jsonText);
  const incoming = Array.isArray(data) ? data : data.snippets;
  if (!Array.isArray(incoming)) throw new Error("not a snippet export");
  const all = listSnippets();
  const byId = new Map(all.map((s) => [s.id, s]));
  let added = 0,
    skipped = 0;
  for (const raw of incoming) {
    if (!raw || typeof raw.code !== "string" || typeof raw.name !== "string") {
      skipped++;
      continue;
    }
    const existing = raw.id ? byId.get(raw.id) : null;
    if (existing && existing.code === raw.code) {
      skipped++;
      continue;
    }
    const snip = {
      id: existing || !raw.id ? newId() : raw.id,
      name: existing ? uniqueName(`${raw.name} (imported)`) : raw.name,
      code: raw.code,
      basedOn: raw.basedOn || null,
      createdAt: raw.createdAt || Date.now(),
      updatedAt: raw.updatedAt || Date.now(),
    };
    all.push(snip);
    byId.set(snip.id, snip);
    added++;
  }
  writeJson(SNIPPETS_KEY, all);
  return { added, skipped };
}

// --- share links ----------------------------------------------------------------

const b64url = (bytes) => {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

const b64urlDecode = (s) => {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
};

async function pump(bytes, stream) {
  const out = new Blob([bytes]).stream().pipeThrough(stream);
  return new Uint8Array(await new Response(out).arrayBuffer());
}

export async function encodeShare(code) {
  const packed = await pump(
    new TextEncoder().encode(code),
    new CompressionStream("deflate-raw")
  );
  return b64url(packed);
}

export async function decodeShare(data) {
  const bytes = await pump(
    b64urlDecode(data),
    new DecompressionStream("deflate-raw")
  );
  return new TextDecoder().decode(bytes);
}
