// float.js — mobile "picture-in-picture" badge.
//
// On narrow screens (matches the CSS `@media (max-width: 900px)` breakpoint)
// the editor should own the whole viewport and the badge should FLOAT over it
// as a small, draggable disc — the screen + LED ring only. A little handle
// expands it into a full overlay that also carries the transport + console.
//
// All the *visual* work lives in style.css behind `body.float-active` /
// `body.badge-expanded`; this file only toggles those classes, drags the disc
// (with a threshold so a tap never presses a badge button), and — crucially —
// tears the whole thing down cleanly when the viewport crosses back above the
// breakpoint (rotation / resize / desktop). It never touches the <canvas>
// node: the disc is positioned via CSS on the existing #badge container.

const BREAKPOINT = "(max-width: 900px)";
const DRAG_THRESHOLD = 6; // px a pointer must travel before it counts as a drag
const EDGE = 10; // keep this many px between the disc and the viewport edge
const SS_KEY = "tildagon.float.pos";

const mql = window.matchMedia(BREAKPOINT);

let pane = null; // #badge-pane — the element we float / drag
let fab = null; // the expand / collapse handle (created lazily)

let active = false;
let expanded = false;

// drag bookkeeping
let pointerId = null;
let dragging = false;
let startX = 0;
let startY = 0;
let startLeft = 0;
let startTop = 0;

// --- position helpers -------------------------------------------------------
function discSize() {
  // The mini disc is square; read its actual CSS-driven size from the DOM so
  // JS and CSS never disagree about the clamp.
  const r = pane.getBoundingClientRect();
  return { w: r.width, h: r.height };
}

function clampPos(x, y, size) {
  const maxX = Math.max(EDGE, window.innerWidth - size.w - EDGE);
  const maxY = Math.max(EDGE, window.innerHeight - size.h - EDGE);
  return {
    x: Math.min(Math.max(EDGE, x), maxX),
    y: Math.min(Math.max(EDGE, y), maxY),
  };
}

function setPos(x, y) {
  const size = discSize();
  const p = clampPos(x, y, size);
  pane.style.setProperty("--fx", `${Math.round(p.x)}px`);
  pane.style.setProperty("--fy", `${Math.round(p.y)}px`);
  return p;
}

function savedPos() {
  try {
    const v = JSON.parse(sessionStorage.getItem(SS_KEY));
    if (v && Number.isFinite(v.x) && Number.isFinite(v.y)) return v;
  } catch {}
  return null;
}

function persistPos() {
  const x = parseFloat(pane.style.getPropertyValue("--fx")) || 0;
  const y = parseFloat(pane.style.getPropertyValue("--fy")) || 0;
  try {
    sessionStorage.setItem(SS_KEY, JSON.stringify({ x, y }));
  } catch {}
}

function placeDefault() {
  const size = discSize();
  const saved = savedPos();
  if (saved) return setPos(saved.x, saved.y);
  // default: tucked into the bottom-right corner
  return setPos(
    window.innerWidth - size.w - EDGE,
    window.innerHeight - size.h - EDGE,
  );
}

// --- expand / collapse ------------------------------------------------------
function setExpanded(next) {
  expanded = next;
  document.body.classList.toggle("badge-expanded", expanded);
  if (fab) {
    fab.textContent = expanded ? "×" : "⤢"; // × / ⤢
    fab.title = expanded ? "shrink the badge" : "expand the badge";
    fab.setAttribute("aria-label", fab.title);
  }
  if (!expanded && active) {
    // re-clamp in case the viewport changed while expanded
    const size = discSize();
    const x = parseFloat(pane.style.getPropertyValue("--fx"));
    const y = parseFloat(pane.style.getPropertyValue("--fy"));
    if (Number.isFinite(x) && Number.isFinite(y)) {
      const p = clampPos(x, y, size);
      setPos(p.x, p.y);
    } else {
      placeDefault();
    }
  }
}

function ensureFab() {
  if (fab) return;
  fab = document.createElement("button");
  fab.className = "badge-fab";
  fab.type = "button";
  fab.textContent = "⤢";
  fab.title = "expand the badge";
  fab.setAttribute("aria-label", fab.title);
  fab.addEventListener("click", (ev) => {
    ev.stopPropagation();
    setExpanded(!expanded);
  });
  // Keep a fab pointerdown from starting a drag on the disc underneath.
  fab.addEventListener("pointerdown", (ev) => ev.stopPropagation());
  pane.appendChild(fab);
}

// --- dragging ---------------------------------------------------------------
function onPointerDown(ev) {
  if (expanded) return; // no dragging in the full overlay
  if (ev.button != null && ev.button !== 0) return;
  if (ev.target.closest(".badge-fab")) return; // let the handle click
  pointerId = ev.pointerId;
  dragging = false;
  startX = ev.clientX;
  startY = ev.clientY;
  startLeft = parseFloat(pane.style.getPropertyValue("--fx")) || 0;
  startTop = parseFloat(pane.style.getPropertyValue("--fy")) || 0;
  window.addEventListener("pointermove", onPointerMove, { passive: false });
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
}

function onPointerMove(ev) {
  if (ev.pointerId !== pointerId) return;
  const dx = ev.clientX - startX;
  const dy = ev.clientY - startY;
  if (!dragging) {
    if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    dragging = true;
    document.body.classList.add("badge-dragging");
    try {
      pane.setPointerCapture(pointerId);
    } catch {}
  }
  ev.preventDefault();
  setPos(startLeft + dx, startTop + dy);
}

function onPointerUp(ev) {
  if (ev.pointerId !== pointerId) return;
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", onPointerUp);
  window.removeEventListener("pointercancel", onPointerUp);
  try {
    pane.releasePointerCapture(pointerId);
  } catch {}
  if (dragging) {
    document.body.classList.remove("badge-dragging");
    persistPos();
  }
  pointerId = null;
  dragging = false;
}

// --- resize (while active, same side of the breakpoint) ---------------------
function onResize() {
  if (!active || expanded) return;
  const x = parseFloat(pane.style.getPropertyValue("--fx"));
  const y = parseFloat(pane.style.getPropertyValue("--fy"));
  if (Number.isFinite(x) && Number.isFinite(y)) setPos(x, y);
}

// --- activate / deactivate --------------------------------------------------
function activate() {
  if (active) return;
  active = true;
  document.body.classList.add("float-active");
  ensureFab();
  // let the new fixed-size styles apply, then position from saved/default
  placeDefault();
  pane.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("resize", onResize);
}

function deactivate() {
  if (!active) return;
  active = false;
  // stop any in-flight drag
  if (pointerId !== null) {
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    pointerId = null;
    dragging = false;
  }
  pane.removeEventListener("pointerdown", onPointerDown);
  window.removeEventListener("resize", onResize);
  document.body.classList.remove(
    "float-active",
    "badge-expanded",
    "badge-dragging",
  );
  expanded = false;
  // wipe the inline position so the desktop layout is byte-for-byte the CSS's
  pane.style.removeProperty("--fx");
  pane.style.removeProperty("--fy");
  if (fab) {
    fab.remove();
    fab = null;
  }
}

function onBreakpoint(e) {
  if (e.matches) activate();
  else deactivate();
}

// ---------------------------------------------------------------------------
export function initFloat() {
  pane = document.querySelector("#badge-pane");
  if (!pane) return null;

  if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
  else mql.addListener(onBreakpoint); // Safari < 14

  if (mql.matches) activate();

  // Small hook for headless QA / console tinkerers.
  return {
    isActive: () => active,
    isExpanded: () => expanded,
    expand: () => active && setExpanded(true),
    collapse: () => active && setExpanded(false),
    toggle: () => active && setExpanded(!expanded),
    pos: () => ({
      x: parseFloat(pane.style.getPropertyValue("--fx")),
      y: parseFloat(pane.style.getPropertyValue("--fy")),
    }),
    moveTo: (x, y) => active && !expanded && setPos(x, y),
  };
}
