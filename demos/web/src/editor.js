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
// 1. Scrubbable number literals
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
  },
  "&.cm-scrubbing, &.cm-scrubbing *": {cursor: "ew-resize !important"},
});

// Drag handler. pointerdown over a number => we own the gesture (pointer
// events, not mousedown: on touch devices the compatibility mousedown fires
// AFTER pointerup, which would leave the window listeners dangling).
// preventDefault stops native selection and the synthesized mouse events; a
// <3px "drag" is treated as a click and places the cursor.
const scrubDragHandler = EditorView.domEventHandlers({
  pointerdown(event, view) {
    if (event.button !== 0) return false;
    const pos = view.posAtCoords({x: event.clientX, y: event.clientY});
    if (pos == null) return false;
    const tok = numberTokenAt(view.state, pos);
    if (!tok) return false;

    event.preventDefault();
    const startX = event.clientX;
    const original = tok.text;
    const {decimals, step} = stepInfo(original);
    const startValue = parseFloat(original);
    const from = tok.from;
    let currentText = original;
    let moved = false;

    const teardown = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", teardown);
      view.dom.classList.remove("cm-scrubbing");
    };

    // The document under the drag must still hold the text we last wrote —
    // if something else changed it (demo switch mid-drag), abort the gesture
    // instead of splicing numbers into unrelated code.
    const docMoved = () =>
      from + currentText.length > view.state.doc.length ||
      view.state.sliceDoc(from, from + currentText.length) !== currentText;

    const onMove = (e) => {
      const dx = e.clientX - startX;
      if (!moved && Math.abs(dx) < 3) return;   // click vs drag threshold
      moved = true;
      if (docMoved()) return teardown();
      view.dom.classList.add("cm-scrubbing");
      // Shift = 10x finer once you want it; Alt = 10x coarser.
      let gain = step;
      if (e.shiftKey) gain = step / 10;
      if (e.altKey) gain = step * 10;
      const value = startValue + Math.round(dx / PX_PER_STEP) * gain;
      const text = formatNumber(value, e.shiftKey ? decimals + 1 : decimals);
      if (text === currentText) return;
      // Live updates bypass history: the whole drag becomes ONE undo step.
      view.dispatch({
        changes: {from, to: from + currentText.length, insert: text},
        annotations: Transaction.addToHistory.of(false),
        userEvent: "input.scrub",
      });
      currentText = text;
    };

    const onUp = (e) => {
      teardown();
      if (!moved) {
        // Plain click: behave like normal cursor placement.
        view.dispatch({selection: {anchor: pos}});
        view.focus();
        return;
      }
      if (currentText !== original && !docMoved()) {
        // Collapse the drag into a single undoable change: silently restore
        // the original, then re-apply the final value WITH history.
        view.dispatch({
          changes: {from, to: from + currentText.length, insert: original},
          annotations: Transaction.addToHistory.of(false),
        });
        view.dispatch({
          changes: {from, to: from + original.length, insert: currentText},
          userEvent: "input.scrub",
        });
      }
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", teardown);
    return true; // tell CodeMirror the event is handled
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
    el.addEventListener("mousedown", (ev) => {
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
  // click() must run in the user gesture
  input.click();
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
  },
});

export const colorSwatches = [swatchPlugin, swatchTheme];

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
        EditorView.updateListener.of((update) => {
          if (!update.docChanged) return;
          // Scrub drags want near-immediate feedback; typing gets debounced.
          const isScrub = update.transactions.some(
            (tr) => tr.isUserEvent("input.scrub"));
          clearTimeout(timer);
          timer = setTimeout(
            () => onChange(update.state.doc.toString()),
            isScrub ? 33 : debounceMs);
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
