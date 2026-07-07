// mpy.js — .py -> .mpy in the browser, via the pinned @pybricks/mpy-cross-v6
// wasm build that build.sh drops into dist/mpy-cross/ (see build.sh for the
// version pin + checksum).
//
// Output is pure-bytecode .mpy v6.0 (header 4D 06 00 1F): loads on every
// MicroPython v6-bytecode firmware (1.19 through 1.28+, sub-version is
// ignored for bytecode-only files) — the Tildagon pin is 1.28.0. No -march
// (would add native-ABI constraints), no -O (keeps line numbers so on-badge
// tracebacks still point at real lines).
//
// The glue re-fetches the wasm on every compile (Emscripten main() is
// one-shot); the browser HTTP cache absorbs it.

const BUILD = typeof __BUILD_ID__ === "string" ? __BUILD_ID__ : "dev";

let modPromise = null;

function loadCompiler() {
  if (!modPromise) {
    // Dynamic URL so esbuild leaves the import alone: the module is a
    // build-time artifact in dist/, not part of this bundle.
    const url = new URL(`mpy-cross/index.js?b=${BUILD}`, document.baseURI).href;
    // Don't cache a rejection — a transient load failure would otherwise
    // poison every future compile. Clear it so the next call retries.
    modPromise = import(url).catch((err) => {
      modPromise = null;
      throw err;
    });
  }
  return modPromise;
}

// Returns Uint8Array of .mpy bytes; throws with the mpy-cross traceback
// (includes "File "app.py", line N") on a compile error.
export async function compileMpy(source) {
  const mod = await loadCompiler();
  // esbuild's CJS->ESM conversion exposes module.exports as `default`
  const compile = mod.compile || mod.default?.compile;
  const wasmUrl = new URL(`mpy-cross/mpy-cross-v6.wasm?b=${BUILD}`, document.baseURI).href;
  const result = await compile("app.py", source, null, wasmUrl);
  if (result.status !== 0 || !result.mpy) {
    throw new Error((result.err || []).join("\n") || "mpy-cross failed");
  }
  return result.mpy;
}
