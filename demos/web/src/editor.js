// editor.js — live-editor pane: CodeMirror 6 + python + oneDark + lint +
// scrubbable number literals (Bret Victor style drag-to-change).
//
// Verified against pinned versions:
//   codemirror@6.0.2  @codemirror/state@6.7.1  @codemirror/view@6.43.5
//   @codemirror/language@6.12.4  @codemirror/lint@6.9.7
//   @codemirror/lang-python@6.2.1  @codemirror/theme-one-dark@6.1.3

import {basicSetup} from "codemirror";
import {EditorView, ViewPlugin, Decoration} from "@codemirror/view";
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

// Drag handler. mousedown over a number => we own the gesture: returning true
// stops CodeMirror's selection handling, preventDefault stops native
// selection. A <3px "drag" is treated as a click and places the cursor.
const scrubDragHandler = EditorView.domEventHandlers({
  mousedown(event, view) {
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

    const onMove = (e) => {
      const dx = e.clientX - startX;
      if (!moved && Math.abs(dx) < 3) return;   // click vs drag threshold
      moved = true;
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
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      view.dom.classList.remove("cm-scrubbing");
      if (!moved) {
        // Plain click: behave like normal cursor placement.
        view.dispatch({selection: {anchor: pos}});
        view.focus();
        return;
      }
      if (currentText !== original) {
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
    return true; // tell CodeMirror the event is handled
  },
});

export const scrubbableNumbers = [scrubHighlighter, scrubTheme, scrubDragHandler];

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
