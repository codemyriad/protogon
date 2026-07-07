// editor.js — live-editor pane: CodeMirror 6 + python + oneDark + lint +
// scrubbable number literals (Bret Victor style drag-to-change).
//
// Verified against pinned versions:
//   codemirror@6.0.2  @codemirror/state@6.7.1  @codemirror/view@6.43.5
//   @codemirror/language@6.12.4  @codemirror/lint@6.9.7
//   @codemirror/lang-python@6.2.1  @codemirror/theme-one-dark@6.1.3

import {basicSetup} from "codemirror";
import {EditorView, ViewPlugin, Decoration, WidgetType} from "@codemirror/view";
import {EditorState, Transaction} from "@codemirror/state";
import {python} from "@codemirror/lang-python";
import {oneDark} from "@codemirror/theme-one-dark";
import {syntaxTree} from "@codemirror/language";
import {setDiagnostics, lintGutter} from "@codemirror/lint";

// ---------------------------------------------------------------------------
// 1. Tweakable number literals
//   desktop: drag a number to scrub it
//   mobile:  double-tap a number to open a slider
//
// A `MIN<var<MAX` annotation anywhere on the line sets the slider's range.
// With one number on the line the letter is usually `n` (`# 3<n<22`); with
// several, letters map to them left-to-right by position:
//   constants = (2.2, 3.3, 4.4)   # 1<a<5  3<b<10  0<c<1
// ---------------------------------------------------------------------------

// Find a plain decimal Number token at `pos`. Returns {from, to, text} with a
// leading unary minus folded in, or null for hex/exponent/complex literals.
function numberTokenAt(state, pos) {
  const tree = syntaxTree(state);
  let node = tree.resolveInner(pos, 1);
  if (node.name !== "Number") node = tree.resolveInner(pos, -1);
  if (node.name !== "Number") return null;
  let {from, to} = node;
  // "-0.05" parses as UnaryExpression(ArithOp, Number): grab the minus too,
  // so scrubbing can cross zero.
  const parent = node.parent;
  if (parent && parent.name === "UnaryExpression" &&
      state.sliceDoc(parent.from, parent.from + 1) === "-") {
    from = parent.from;
  }
  const text = state.sliceDoc(from, to);
  // Only scrub plain ints/floats. Bail on 0xFF, 1e-3, 1_000, 3j, etc.
  if (!/^-?\d+(\.\d+)?$/.test(text)) return null;
  return {from, to, text};
}

// "0.35" -> {decimals: 2, step: 0.01}; "13" -> {decimals: 0, step: 1}.
// SCRUB_GAIN trades pixels for steps; raise DRAG_COARSENESS to e.g. 5 if you
// want 0.35 to move in 0.05 jumps instead of 0.01.
const PX_PER_STEP = 8;        // horizontal pixels per increment
const DRAG_COARSENESS = 1;    // multiply the base step (1 => last decimal place)
function stepInfo(text) {
  const dot = text.indexOf(".");
  const decimals = dot === -1 ? 0 : text.length - dot - 1;
  return {decimals, step: Math.pow(10, -decimals) * DRAG_COARSENESS};
}

function formatNumber(value, decimals) {
  // toFixed keeps the visual precision of the original literal ("0.35" stays
  // 2-decimal while scrubbing; "13" stays an int).
  let s = value.toFixed(decimals);
  if (s === "-0" || /^-0\.0+$/.test(s)) s = s.slice(1); // avoid "-0.00"
  return s;
}

// Decorate visible Number tokens so CSS can show an ew-resize cursor.
const scrubMark = Decoration.mark({class: "cm-scrubbable"});
const scrubHighlighter = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = this.compute(view); }
  update(u) {
    if (u.docChanged || u.viewportChanged) this.decorations = this.compute(u.view);
  }
  compute(view) {
    const marks = [];
    for (const {from, to} of view.visibleRanges) {
      syntaxTree(view.state).iterate({
        from, to,
        enter(node) {
          if (node.name === "Number") {
            const tok = numberTokenAt(view.state, node.from);
            if (tok) marks.push(scrubMark.range(tok.from, tok.to));
          }
        },
      });
    }
    return Decoration.set(marks, true);
  }
}, {decorations: v => v.decorations});

const scrubTheme = EditorView.baseTheme({
  ".cm-scrubbable": {
    cursor: "ew-resize",
    borderBottom: "1px dotted currentColor",
    // Kill the mobile double-tap-to-zoom delay so our own double-tap (which
    // opens the slider) fires promptly; normal scrolling is untouched.
    touchAction: "manipulation",
  },
  "&.cm-scrubbing, &.cm-scrubbing *": {cursor: "ew-resize !important"},
  ".cm-slider-pop": {
    position: "fixed",
    zIndex: "60",
    display: "flex",
    alignItems: "center",
    gap: "0.6rem",
    padding: "0.5rem 0.7rem",
    background: "#1b1f23",
    border: "1px solid #2a3036",
    borderRadius: "8px",
    boxShadow: "0 8px 26px rgba(0,0,0,0.5)",
    font: "13px system-ui, sans-serif",
    color: "#d6dbe0",
  },
  ".cm-slider-pop input[type=range]": {
    width: "min(60vw, 220px)",
    accentColor: "#afc944",
    touchAction: "none",
  },
  ".cm-slider-val": {
    minWidth: "3.2em",
    textAlign: "right",
    fontVariantNumeric: "tabular-nums",
    color: "#afc944",
    fontWeight: "600",
  },
});

// --- range annotations -----------------------------------------------------

// The plain int/float literals on `line`, left to right.
function lineNumberTokens(state, line) {
  const tokens = [];
  syntaxTree(state).iterate({
    from: line.from,
    to: line.to,
    enter(node) {
      if (node.name === "Number") {
        const tok = numberTokenAt(state, node.from);
        if (tok) tokens.push(tok);
      }
    },
  });
  return tokens;
}

// Map each annotated literal to its {min, max}. `n` targets the single value;
// otherwise a=1st, b=2nd, c=3rd, … The MIN/MAX live in a comment, so they are
// not Number tokens and never collide with the code literals.
function parseLineRanges(state, line) {
  const tokens = lineNumberTokens(state, line);
  const ranges = new Map(); // literal.from -> {min, max}
  const re = /(-?\d*\.?\d+)\s*<\s*([a-zA-Z])\s*<\s*(-?\d*\.?\d+)/g;
  let m;
  while ((m = re.exec(line.text))) {
    const min = parseFloat(m[1]);
    const max = parseFloat(m[3]);
    const letter = m[2].toLowerCase();
    let idx = letter === "n" && tokens.length === 1 ? 0 : letter.charCodeAt(0) - 97;
    if (idx >= 0 && idx < tokens.length && max > min) {
      ranges.set(tokens[idx].from, { min, max });
    }
  }
  return ranges;
}

function rangeForToken(state, tok) {
  const line = state.doc.lineAt(tok.from);
  return parseLineRanges(state, line).get(tok.from) || null;
}

// A sensible slider range when the line carries no annotation.
function defaultRange(value) {
  if (value > 0 && value <= 1) return { min: 0, max: 1 };
  if (value === 0) return { min: 0, max: 1 };
  if (value > 0) return { min: 0, max: value * 4 };
  return { min: value * 4, max: 0 };
}

function decimalsForStep(step) {
  if (step >= 1) return 0;
  const s = step.toExponential(); // e.g. "1e-2"
  const exp = parseInt(s.slice(s.indexOf("e") + 1), 10);
  return Math.max(0, -exp);
}

// --- the slider popup (mobile double-tap) ----------------------------------

let activeSlider = null;
function closeActiveSlider() {
  if (activeSlider) activeSlider();
  activeSlider = null;
}

function openSlider(view, tok) {
  closeActiveSlider();
  const decimals = stepInfo(tok.text).decimals;
  const startValue = parseFloat(tok.text);
  const rng = rangeForToken(view.state, tok) || defaultRange(startValue);
  // The starting value must fit inside the track.
  const lo = Math.min(rng.min, startValue);
  const hi = Math.max(rng.max, startValue);
  let step = decimals > 0 ? Math.pow(10, -Math.max(decimals, 2)) : 1;
  while ((hi - lo) / step > 2000) step *= 10; // keep the track manageable
  const outDecimals = Math.max(decimals, decimalsForStep(step));

  const from = tok.from;
  const original = tok.text;
  let currentText = original;

  const docMoved = () =>
    from + currentText.length > view.state.doc.length ||
    view.state.sliceDoc(from, from + currentText.length) !== currentText;

  const apply = (value, withHistory) => {
    if (docMoved()) return;
    const text = formatNumber(value, outDecimals);
    if (text === currentText && !withHistory) return;
    const spec = {
      changes: { from, to: from + currentText.length, insert: text },
      userEvent: "input.pick", // fast live-swap path, same as scrubbing
    };
    if (!withHistory) spec.annotations = Transaction.addToHistory.of(false);
    view.dispatch(spec);
    currentText = text;
  };

  const pop = document.createElement("div");
  pop.className = "cm-slider-pop";
  const range = document.createElement("input");
  range.type = "range";
  range.min = String(lo);
  range.max = String(hi);
  range.step = String(step);
  range.value = String(startValue);
  const val = document.createElement("span");
  val.className = "cm-slider-val";
  val.textContent = formatNumber(startValue, outDecimals);
  pop.append(range, val);
  document.body.appendChild(pop);

  const coords = view.coordsAtPos(from);
  if (coords) {
    const w = pop.offsetWidth || 280;
    pop.style.left = Math.max(6, Math.min(coords.left, window.innerWidth - w - 6)) + "px";
    const below = coords.bottom + 8;
    pop.style.top =
      (below + pop.offsetHeight < window.innerHeight ? below : coords.top - pop.offsetHeight - 8) + "px";
  }

  range.addEventListener("input", () => {
    const v = parseFloat(range.value);
    val.textContent = formatNumber(v, outDecimals);
    apply(v, false);
  });

  const close = () => {
    document.removeEventListener("pointerdown", onOutside, true);
    pop.remove();
    // Collapse the whole session into one undo step.
    if (currentText !== original && !docMoved()) {
      const finalText = currentText;
      view.dispatch({
        changes: { from, to: from + finalText.length, insert: original },
        annotations: Transaction.addToHistory.of(false),
      });
      view.dispatch({
        changes: { from, to: from + original.length, insert: finalText },
        userEvent: "input.pick",
      });
    }
  };
  const onOutside = (e) => {
    if (!pop.contains(e.target)) closeActiveSlider();
  };
  // Defer so the tap that opened us doesn't immediately close it.
  setTimeout(() => document.addEventListener("pointerdown", onOutside, true), 0);

  activeSlider = close;
}

// --- pointer handler: mouse drags, touch double-taps -----------------------

// Double-tap tracking (mobile). Two taps on the same literal within 400 ms.
let lastTapFrom = -1;
let lastTapAt = 0;
function isSecondTap(from) {
  const now = performance.now();
  const dbl = from === lastTapFrom && now - lastTapAt < 400;
  lastTapFrom = dbl ? -1 : from;
  lastTapAt = now;
  return dbl;
}

const scrubDragHandler = EditorView.domEventHandlers({
  pointerdown(event, view) {
    if (event.button !== 0) return false;
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY });
    if (pos == null) return false;
    const tok = numberTokenAt(view.state, pos);
    if (!tok) return false;

    // Mobile: no swipe-scrub. A double-tap opens the slider; a single tap
    // falls through to normal cursor placement.
    if (event.pointerType === "touch") {
      if (isSecondTap(tok.from)) {
        event.preventDefault();
        openSlider(view, tok);
        return true;
      }
      return false;
    }

    // Desktop mouse / pen: drag to scrub.
    event.preventDefault();
    const startX = event.clientX;
    const original = tok.text;
    const { decimals, step } = stepInfo(original);
    const startValue = parseFloat(original);
    const from = tok.from;
    let currentText = original;
    let moved = false;

    const teardown = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      view.dom.classList.remove("cm-scrubbing");
    };

    const docMoved = () =>
      from + currentText.length > view.state.doc.length ||
      view.state.sliceDoc(from, from + currentText.length) !== currentText;

    const onMove = (e) => {
      const dx = e.clientX - startX;
      if (!moved && Math.abs(dx) < 3) return; // click vs drag threshold
      moved = true;
      if (docMoved()) return teardown();
      view.dom.classList.add("cm-scrubbing");
      let gain = step; // Shift = 10x finer, Alt = 10x coarser
      if (e.shiftKey) gain = step / 10;
      if (e.altKey) gain = step * 10;
      const value = startValue + Math.round(dx / PX_PER_STEP) * gain;
      const text = formatNumber(value, e.shiftKey ? decimals + 1 : decimals);
      if (text === currentText) return;
      view.dispatch({
        changes: { from, to: from + currentText.length, insert: text },
        annotations: Transaction.addToHistory.of(false),
        userEvent: "input.scrub",
      });
      currentText = text;
    };

    const onUp = () => {
      teardown();
      if (!moved) {
        view.dispatch({ selection: { anchor: pos } });
        view.focus();
        return;
      }
      if (currentText !== original && !docMoved()) {
        // Collapse the drag into a single undoable change.
        view.dispatch({
          changes: { from, to: from + currentText.length, insert: original },
          annotations: Transaction.addToHistory.of(false),
        });
        view.dispatch({
          changes: { from, to: from + original.length, insert: currentText },
          userEvent: "input.scrub",
        });
      }
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return true;
  },
});

export const scrubbableNumbers = [scrubHighlighter, scrubTheme, scrubDragHandler];

// ---------------------------------------------------------------------------
// 1b. Colour swatches
//
// Three number literals that form a colour — ctx.rgb(r, g, b) /
// ctx.rgba(r, g, b, a) arguments, or a bare (r, g, b) tuple with every value
// in 0..1 — get a clickable swatch. Clicking opens the native colour picker;
// picking rewrites the three literals live (same fast path as scrubbing).
// ---------------------------------------------------------------------------

// Collect [{from, to, text}] for the leading three plain Number children of
// a node, or null. exact3: the node must contain exactly three values
// (a bare colour tuple); otherwise only the first three must be numbers
// (rgb/rgba args — alpha may be a variable).
function colorNumbers(state, node, exact3) {
  const kids = [];
  for (let child = node.firstChild; child; child = child.nextSibling) {
    if (child.name === "(" || child.name === ")" || child.name === ",") continue;
    kids.push(child);
  }
  if (exact3 ? kids.length !== 3 : kids.length < 3) return null;
  const three = kids.slice(0, 3);
  if (!three.every((k) => k.name === "Number")) return null;
  const nums = three.map((k) => ({from: k.from, to: k.to,
                                  text: state.sliceDoc(k.from, k.to)}));
  for (const n of nums) {
    if (!/^\d+(\.\d+)?$/.test(n.text)) return null;
    if (parseFloat(n.text) > 1.0) return null;
  }
  return nums;
}

// Find colour groups in the visible ranges: {pos, nums, hex}
function findColorGroups(view) {
  const groups = [];
  const {state} = view;
  for (const {from, to} of view.visibleRanges) {
    syntaxTree(state).iterate({
      from, to,
      enter(node) {
        let nums = null;
        if (node.name === "ArgList") {
          const call = node.node.parent;
          if (!call || call.name !== "CallExpression") return;
          const callee = state.sliceDoc(call.from, node.from);
          if (!/\.(rgb|rgba)$/.test(callee)) return;
          nums = colorNumbers(state, node.node, false);
        } else if (node.name === "TupleExpression") {
          nums = colorNumbers(state, node.node, true);
        }
        if (!nums) return;
        const hex = "#" + nums.map((n) => {
          const v = Math.round(Math.min(1, Math.max(0, parseFloat(n.text))) * 255);
          return v.toString(16).padStart(2, "0");
        }).join("");
        groups.push({pos: nums[0].from, nums, hex});
      },
    });
  }
  return groups;
}

function formatChannel(v) {
  let s = v.toFixed(2);
  if (s.endsWith("0")) s = s.slice(0, -1);   // "1.00" -> "1.0", "0.50" -> "0.5"
  return s;
}

class SwatchWidget extends WidgetType {
  constructor(hex, nums) {
    super();
    this.hex = hex;
    this.nums = nums;
  }

  eq(other) {
    return other.hex === this.hex && other.nums[0].from === this.nums[0].from;
  }

  toDOM(view) {
    const el = document.createElement("span");
    el.className = "cm-color-swatch";
    el.style.background = this.hex;
    el.title = "pick a colour";
    // pointerdown, not mousedown: on touch the synthesized mousedown may never
    // fire on a tiny inline widget, and it wouldn't carry the user-activation
    // the native colour picker needs. pointerdown covers mouse + touch + pen.
    el.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openPicker(view, el, this.hex, this.nums);
    });
    return el;
  }

  ignoreEvent() {
    return true;
  }
}

function openPicker(view, anchor, hex, nums) {
  const input = document.createElement("input");
  input.type = "color";
  input.className = "cm-color-input";
  input.value = hex;
  const rect = anchor.getBoundingClientRect();
  input.style.position = "fixed";
  input.style.left = rect.left + "px";
  input.style.top = rect.bottom + "px";
  input.style.opacity = "0";
  input.style.width = "1px";
  input.style.height = "1px";
  document.body.appendChild(input);

  // Track each literal's live range: lengths change as we rewrite them.
  const current = nums.map((n) => ({from: n.from, text: n.text}));
  const original = nums.map((n) => n.text);

  const docMoved = () =>
    current.some((c) =>
      c.from + c.text.length > view.state.doc.length ||
      view.state.sliceDoc(c.from, c.from + c.text.length) !== c.text);

  // Replace the three literals in one transaction and update the tracked
  // ranges (CodeMirror maps the simultaneous changes; only lengths shift).
  const rewrite = (texts, withHistory) => {
    if (docMoved()) return false;
    const spec = {
      changes: current.map((c, i) => ({
        from: c.from,
        to: c.from + c.text.length,
        insert: texts[i],
      })),
      userEvent: "input.scrub",
    };
    if (!withHistory) spec.annotations = Transaction.addToHistory.of(false);
    view.dispatch(spec);
    let shift = 0;
    for (let i = 0; i < 3; i++) {
      current[i].from += shift;
      shift += texts[i].length - current[i].text.length;
      current[i].text = texts[i];
    }
    return true;
  };

  const hexToTexts = (value) =>
    [1, 3, 5].map((i) => formatChannel(parseInt(value.slice(i, i + 2), 16) / 255));

  input.addEventListener("input", () => rewrite(hexToTexts(input.value), false));
  input.addEventListener("change", () => {
    // Collapse the whole picking session into one undoable change: silently
    // restore the originals, then re-apply the final colour WITH history.
    if (current.some((c, i) => c.text !== original[i])) {
      const finals = current.map((c) => c.text);
      if (rewrite(original.slice(), false)) rewrite(finals, true);
    }
    input.remove();
  });
  // Open the native picker. showPicker() is the API that actually works on
  // mobile — a programmatic input.click() opens nothing there. Both need the
  // live user gesture we're inside (this runs synchronously from pointerdown).
  try {
    if (typeof input.showPicker === "function") input.showPicker();
    else input.click();
  } catch {
    input.click();
  }
}

const swatchPlugin = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = this.compute(view); }
  update(u) {
    if (u.docChanged || u.viewportChanged) this.decorations = this.compute(u.view);
  }
  compute(view) {
    const widgets = findColorGroups(view).map((g) =>
      Decoration.widget({widget: new SwatchWidget(g.hex, g.nums), side: -1})
        .range(g.pos));
    return Decoration.set(widgets, true);
  }
}, {decorations: (v) => v.decorations});

const swatchTheme = EditorView.baseTheme({
  ".cm-color-swatch": {
    display: "inline-block",
    width: "0.85em",
    height: "0.85em",
    borderRadius: "3px",
    border: "1px solid rgba(255,255,255,0.4)",
    marginRight: "5px",
    verticalAlign: "-0.1em",
    cursor: "pointer",
    touchAction: "none",
  },
});

export const colorSwatches = [swatchPlugin, swatchTheme];

// ---------------------------------------------------------------------------
// 1c. Pick-one groups — "comment/uncomment to switch", made clickable
//
// A run of adjacent lines at the same indent, each tagged with a `#: label`
// marker, is a radio group: exactly the uncommented one runs, the rest are
// commented out. Clicking a choice comments the active line and uncomments
// the clicked one — one transaction, so the badge swaps to it live. It stays
// plain Python: `#: label` is just a comment, and you can still edit any line
// or comment them yourself.
//
//     return math.sin(t + x)          #: waves      <- runs
//     # return math.sin(t * 2 + i)    #: spin       <- click to run
// ---------------------------------------------------------------------------

// Parse one line. Returns {indent, commented, marker} where marker is the
// index of "#:" in the line, or null if it isn't a choice line.
function parseChoiceLine(text) {
  const marker = text.indexOf("#:");
  if (marker < 0) return null;
  const head = text.slice(0, marker);
  // head is: <indent>[# ]<code with at least one non-space char><spaces>
  const m = /^(\s*)(#\s?)?(\S.*\S|\S)\s*$/.exec(head);
  if (!m) return null;
  const label = text.slice(marker + 2).trim();
  if (!label) return null;
  return { indent: m[1], commented: !!m[2], marker, label };
}

// The line numbers (1-based) of the choice group containing `lineNo`, or null
// if that line isn't part of a group of 2+ at a consistent indent.
function choiceGroupAt(state, lineNo) {
  const here = parseChoiceLine(state.doc.line(lineNo).text);
  if (!here) return null;
  const lines = [lineNo];
  for (let n = lineNo - 1; n >= 1; n--) {
    const p = parseChoiceLine(state.doc.line(n).text);
    if (!p || p.indent !== here.indent) break;
    lines.unshift(n);
  }
  for (let n = lineNo + 1; n <= state.doc.lines; n++) {
    const p = parseChoiceLine(state.doc.line(n).text);
    if (!p || p.indent !== here.indent) break;
    lines.push(n);
  }
  return lines.length >= 2 ? lines : null;
}

class PickWidget extends WidgetType {
  constructor(active, label, lineNo) {
    super();
    this.active = active;
    this.label = label;
    this.lineNo = lineNo;
  }
  eq(o) {
    return o.active === this.active && o.label === this.label && o.lineNo === this.lineNo;
  }
  toDOM(view) {
    const el = document.createElement("span");
    el.className = "cm-pick" + (this.active ? " cm-pick-on" : "");
    el.textContent = (this.active ? "◉ " : "○ ") + this.label;
    el.title = this.active ? "running — tap another to switch" : `tap to run: ${this.label}`;
    el.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      pickChoice(view, this.lineNo);
    });
    return el;
  }
  ignoreEvent() {
    return true;
  }
}

// Activate the choice on `lineNo`: uncomment it, comment every other active
// line in its group. One transaction => the editor's change listener fires
// once and the badge swaps live.
function pickChoice(view, lineNo) {
  const group = choiceGroupAt(view.state, lineNo);
  if (!group) return;
  const changes = [];
  for (const n of group) {
    const line = view.state.doc.line(n);
    const p = parseChoiceLine(line.text);
    if (!p) continue;
    const shouldComment = n !== lineNo;
    if (shouldComment && !p.commented) {
      const at = line.from + p.indent.length;
      changes.push({ from: at, to: at, insert: "# " });
    } else if (!shouldComment && p.commented) {
      const at = line.from + p.indent.length;
      const rm = /^#\s?/.exec(line.text.slice(p.indent.length))[0].length;
      changes.push({ from: at, to: at + rm, insert: "" });
    }
  }
  if (changes.length) view.dispatch({ changes, userEvent: "input.pick" });
}

const pickPlugin = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = this.compute(view);
    }
    update(u) {
      if (u.docChanged || u.viewportChanged) this.decorations = this.compute(u.view);
    }
    compute(view) {
      const { state } = view;
      const marks = [];
      const seen = new Set();
      for (const { from, to } of view.visibleRanges) {
        let lineNo = state.doc.lineAt(from).number;
        const lastLine = state.doc.lineAt(to).number;
        for (; lineNo <= lastLine; lineNo++) {
          if (seen.has(lineNo)) continue;
          const group = choiceGroupAt(state, lineNo);
          if (!group) continue;
          for (const n of group) {
            seen.add(n);
            const line = state.doc.line(n);
            const p = parseChoiceLine(line.text);
            const start = line.from + p.marker;
            marks.push(
              Decoration.replace({
                widget: new PickWidget(!p.commented, p.label, n),
              }).range(start, line.to)
            );
          }
        }
      }
      marks.sort((a, b) => a.from - b.from);
      return Decoration.set(marks);
    }
  },
  { decorations: (v) => v.decorations }
);

const pickTheme = EditorView.baseTheme({
  ".cm-pick": {
    cursor: "pointer",
    fontSize: "0.85em",
    padding: "0.1em 0.5em",
    marginLeft: "0.3em",
    borderRadius: "999px",
    border: "1px solid rgba(255,255,255,0.18)",
    color: "#8b96a0",
    userSelect: "none",
    touchAction: "none",
  },
  ".cm-pick:hover": { borderColor: "rgba(255,255,255,0.4)", color: "#d6dbe0" },
  ".cm-pick-on": {
    color: "#10130a",
    background: "#afc944",
    borderColor: "#afc944",
    fontWeight: "600",
  },
});

export const pickGroups = [pickPlugin, pickTheme];

// ---------------------------------------------------------------------------
// 1d. Boolean toggles — click a `FLAG = True/False` constant to flip it.
//
// Only bare-name assignments (`WOBBLE = True`) get the affordance — not every
// True/False in the file. A `ctx.arc(..., True)` argument or a `self.x = False`
// in __init__ is not something you'd want to flip with a stray click.
// ---------------------------------------------------------------------------
const boolMark = Decoration.mark({ class: "cm-bool" });

// True if `node` (a Boolean) is the value of a top-levelish `NAME = True/False`.
function isFlagAssignment(node) {
  const parent = node.parent;
  if (!parent || parent.name !== "AssignStatement") return false;
  const first = parent.firstChild;
  return first && first.name === "VariableName";
}

const boolHighlighter = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = this.compute(view);
    }
    update(u) {
      if (u.docChanged || u.viewportChanged) this.decorations = this.compute(u.view);
    }
    compute(view) {
      const marks = [];
      for (const { from, to } of view.visibleRanges) {
        syntaxTree(view.state).iterate({
          from,
          to,
          enter(node) {
            if (node.name === "Boolean" && isFlagAssignment(node.node)) {
              marks.push(boolMark.range(node.from, node.to));
            }
          },
        });
      }
      return Decoration.set(marks);
    }
  },
  { decorations: (v) => v.decorations }
);

const boolClick = EditorView.domEventHandlers({
  pointerdown(event, view) {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !target.classList.contains("cm-bool")) return false;
    const pos = view.posAtDOM(target);
    const tree = syntaxTree(view.state);
    let node = tree.resolveInner(pos, 1);
    if (node.name !== "Boolean") node = tree.resolveInner(pos + 1, -1);
    if (node.name !== "Boolean") return false;
    const text = view.state.sliceDoc(node.from, node.to);
    const flipped = text === "True" ? "False" : "True";
    event.preventDefault();
    view.dispatch({
      changes: { from: node.from, to: node.to, insert: flipped },
      userEvent: "input.pick",
    });
    return true;
  },
});

const boolTheme = EditorView.baseTheme({
  ".cm-bool": {
    cursor: "pointer",
    borderBottom: "1px dotted currentColor",
    touchAction: "none",
  },
});

export const boolToggles = [boolHighlighter, boolClick, boolTheme];

// ---------------------------------------------------------------------------
// 2. Editor construction + live-run plumbing
// ---------------------------------------------------------------------------

export function createEditor({parent, doc, onChange, debounceMs = 200}) {
  let timer = null;
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc,
      extensions: [
        basicSetup,
        python(),
        oneDark,
        lintGutter(),
        scrubbableNumbers,
        colorSwatches,
        pickGroups,
        boolToggles,
        EditorView.updateListener.of((update) => {
          if (!update.docChanged) return;
          // Direct manipulation (scrub, pick-a-choice, toggle) wants
          // near-immediate feedback; typing gets debounced.
          const isDirect = update.transactions.some(
            (tr) => tr.isUserEvent("input.scrub") || tr.isUserEvent("input.pick"));
          clearTimeout(timer);
          timer = setTimeout(
            () => onChange(update.state.doc.toString()),
            isDirect ? 33 : debounceMs);
        }),
      ],
    }),
  });
  return view;
}

// Show a runtime error at a 1-based line number; message stays until cleared.
export function showRuntimeError(view, lineNumber, message) {
  const docLines = view.state.doc.lines;
  const n = Math.min(Math.max(lineNumber, 1), docLines);
  const line = view.state.doc.line(n);
  view.dispatch(setDiagnostics(view.state, [{
    from: line.from,
    to: line.to,
    severity: "error",
    message,
  }]));
}

export function clearRuntimeError(view) {
  view.dispatch(setDiagnostics(view.state, []));
}

// Replace the whole document (demo switching). One transaction, undoable.
export function replaceDoc(view, text) {
  view.dispatch({
    changes: {from: 0, to: view.state.doc.length, insert: text},
    selection: {anchor: 0},
    scrollIntoView: true,
    userEvent: "input.replace",
  });
}
