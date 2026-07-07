# Tildagon live playground

The demos in this folder, running in a web page — next to their source code,
live. Edit the code and the badge changes as you type: no run button, no
reload, no install. Break the code and the badge keeps running the last
working version while the error is pinned to the offending line.

Direct-manipulation editing: **drag** any number literal to change it, or
**double-click** it (**tap** on a touchscreen) for a slider; **tap** a colour
swatch for a picker, **tap** a `#:` pick-one choice to swap it live, **tap** a
`FLAG = True/False`. A `# MIN<n<MAX` comment on a line sets that number's slider
range and clamps its drag (with several numbers on a line, `a`/`b`/`c`/… pick
them by position). Pause badge time and edits re-render the frozen frame.

Every page is one demo: `/#tixy`, `/#ledring`, … The **▤ browse flyout** (icon
dock, far left) lists all fifteen — and your own snippets — as cards, each
with a thumbnail drawn as the **round badge screen**. Demo thumbnails are
**bundled**: emulator-captured frames committed as `demos/<name>/preview.png`
and shipped by `build.sh`. **Your scripts** (snippets and edited demos) are
captured live in the browser — a frame ~3 s after the script starts, cached
in `localStorage` and regenerated when the code changes; a background worker
quietly fills in snippets you haven't run yet. Cards carry quick actions —
⚡ flash, ⧉ duplicate, ✕ delete — and a search box filters both sections. The
`?` button explains the interaction model in an info window.

To regenerate the bundled demo previews after changing a demo (browser
console on the playground, then save each entry of the returned map over
`demos/<id>/preview.png` and rebuild):

```js
await playground.previews.renderPreviewPack(playground.library.demoSources())
```

## Keep your own snippets

The demos are read-only starting points. The moment you edit one, the toolbar
lets you **save** it as your own snippet (they live in `localStorage`); from
there **duplicate** variants, **rename**, **revert**. Unsaved edits autosave
as a draft keyed to what you were editing, so closing the tab never loses
work. `＋ new` starts from a small template. The `⋯` menu **downloads a
`.py`**, duplicates or deletes the open snippet, and **backs up all your
snippets** as a zip of `.py` files (plus a `snippets.json` manifest, so a
future import can restore them losslessly). Share links (`#gz/…` URLs, the
whole program deflate-packed into the URL) still resolve.

The byte counter next to the name shows the size after comments are stripped,
against the ~6.5 KB a hexpansion EEPROM holds — it turns amber, then red, as
you approach the limit.

## Flash it to a hexpansion

`⚡ flash…` writes the current program to a
[Protogon](https://github.com/codemyriad/protogon) (or any writable hexpansion
EEPROM) over USB, straight from the browser — no `mpremote`, no toolchain. It
speaks the MicroPython raw-REPL protocol over
[WebSerial](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API)
(Chrome/Edge on a computer), scans all six ports, and shows which EEPROMs are
writable (a write-protected chip ACKs and silently drops writes, so it probes
by writing and reading back). Pick a port, pick `app.py` (source, comments
stripped) or `app.mpy` (compiled to bytecode in the browser, roughly half the
size), and it flashes with a live progress log, then reboots the badge so your
app mounts and runs.

Needs badge firmware **v1.12.0+** — older firmware can't read the Zetta EEPROM
and wedges the slot on insert; the dialog warns if it sees an older version.
`?mockserial=1` runs the whole flow against a fake badge for testing.

## Run it

```sh
./build.sh          # needs bash, curl, tar, python3, node >= 20
python3 serve.py    # http://localhost:8343/
```

`build.sh` produces `dist/`, a fully static site (~15 MB, ~7 MB over the
wire) with no runtime dependency on any CDN. Any static host works; no
special headers are required (COOP/COEP are nice-to-have, see `serve.py`).

## What's actually running

This is not a reimplementation of the badge — it is the **official EMF
Tildagon firmware and simulator running in the browser**:

- **`ctx.wasm`** — the badge's real C renderer (the exact WebAssembly build
  shipped in `badge-2024-software/sim`), instantiated natively by the browser
  with a ~40-line WASI shim. Same fonts, same antialiasing, same colours as
  the desktop sim.
- **Firmware Python** — `system.scheduler`, `system.eventbus`, `app.App`,
  `events.input` … imported unmodified from the pinned firmware tree and run
  under [Pyodide](https://pyodide.org) (CPython in WebAssembly).
- **Sim fakes** — the official `sim/fakes` shadow modules, with three files
  replaced for the browser (`overlay/`): `ctx.py` (wasmtime → native
  WebAssembly via the `chost` JS bridge), `_sim.py` (pygame window → canvas +
  DOM), `time.py` (wall clock → a host-controlled virtual clock, which is
  what makes pause/step/speed work), plus a tiny `pygame.py` stub for the
  fakes that import it.

Everything runs in a Web Worker, so a runaway edit (`while True:`) can never
freeze the editor — a watchdog reboots the badge with the last good code.

The live-editing loop: each keystroke (debounced ~200 ms, ~33 ms while
scrubbing a number) re-executes the source, instantiates the app class,
migrates simple scalar state (`t`, `mode`, `speed`, …) from the running
instance so the animation never restarts, probes one hidden update+draw
frame to reject broken code before it can take the screen, then swaps the
instance through the firmware's own `RequestStopAppEvent` /
`RequestStartAppEvent`. An app can override the state heuristic by defining
`__live_state__ = ("t", "speed")` — listing exactly which scalars to carry, so
a value the user just picked (a formula, a palette) is deliberately left out
and takes effect immediately.

## Layout

| Path | What |
|---|---|
| `build.sh` | assemble `dist/` (downloads pyodide + firmware + mpy-cross, pinned) |
| `serve.py` | dev server with the right mime types + isolation headers |
| `boot.py` | Pyodide-side bootstrap: sys.path, crash hook, scheduler boot, hot-swap |
| `overlay/` | the three browser fakes + pygame stub (see above) |
| `src/sim-worker.js` | the worker: WASI shim, Pyodide boot, `chost` bridge |
| `src/app.js` | the page: dock + flyout + info chrome, badge, transport, watchdog |
| `src/editor.js` | CodeMirror 6: scrub, colour swatch, pick-one, bool toggle, error pinning |
| `src/store.js` | snippet + draft storage, share-link encode, JSON export/import |
| `src/library.js` | the gallery cards + snippet toolbar, hash routing, size gauge |
| `src/previews.js` | thumbnails: bundled demo art, live capture cache, dock tile, pre-gen |
| `src/flash.js` | the `⚡ flash…` dialog: connect → scan → pick → flash |
| `src/serial.js` | WebSerial MicroPython raw-REPL client (mpremote, in the page) |
| `src/badge-scripts.js` | the Python run on the badge to scan + flash EEPROMs |
| `src/mpy.js` | `.py → .mpy` via the bundled mpy-cross wasm |
| `src/mockserial.js` | fake badge for `?mockserial=1` (headless flash QA) |
| `src/float.js` | mobile picture-in-picture badge (draggable, expandable) |

Pinned versions: pyodide `314.0.2`, `badge-2024-software`
`517f12c478ddef7bd86f277bd30c7f0ee6cb1874`, `@pybricks/mpy-cross-v6` `2.0.0`
(emits pure-bytecode `.mpy` v6), CodeMirror packages in `package.json`.

## Credits

The firmware, simulator, `ctx.wasm` and the badge artwork
(`sim/background.png`) are from
[emfcamp/badge-2024-software](https://github.com/emfcamp/badge-2024-software)
(MIT, © Electromagnetic Field — license ships in `dist/`). The simulator
lineage goes back to the flow3r badge team. The interaction ideas — live
scrubbing, never-stop execution, edit-the-frozen-frame — are borrowed with
admiration from Bret Victor's
[Learnable Programming](https://worrydream.com/LearnableProgramming/).
