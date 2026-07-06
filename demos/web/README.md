# Tildagon live playground

The demos in this folder, running in a web page — next to their source code,
live. Edit the code and the badge changes as you type: no run button, no
reload, no install. Break the code and the badge keeps running the last
working version while the error is pinned to the offending line. Drag any
number literal to scrub it. Pause badge time and edits re-render the frozen
frame.

Every page is one demo: `/#uan`, `/#ten`, … The chips at the top switch
between all fourteen.

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
`__live_state__ = ("t", "mode")`.

## Layout

| Path | What |
|---|---|
| `build.sh` | assemble `dist/` (downloads pyodide + firmware, pinned) |
| `serve.py` | dev server with the right mime types + isolation headers |
| `boot.py` | Pyodide-side bootstrap: sys.path, crash hook, scheduler boot, hot-swap |
| `overlay/` | the three browser fakes + pygame stub (see above) |
| `src/sim-worker.js` | the worker: WASI shim, Pyodide boot, `chost` bridge |
| `src/app.js` | the page: badge chrome, gallery, transport, watchdog |
| `src/editor.js` | CodeMirror 6 + scrubbable numbers + error pinning |

Pinned versions: pyodide `314.0.2`, `badge-2024-software`
`517f12c478ddef7bd86f277bd30c7f0ee6cb1874`, CodeMirror packages in
`package.json`.

## Credits

The firmware, simulator, `ctx.wasm` and the badge artwork
(`sim/background.png`) are from
[emfcamp/badge-2024-software](https://github.com/emfcamp/badge-2024-software)
(MIT, © Electromagnetic Field — license ships in `dist/`). The simulator
lineage goes back to the flow3r badge team. The interaction ideas — live
scrubbing, never-stop execution, edit-the-frozen-frame — are borrowed with
admiration from Bret Victor's
[Learnable Programming](https://worrydream.com/LearnableProgramming/).
