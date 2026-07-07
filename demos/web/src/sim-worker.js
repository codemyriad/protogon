// sim-worker.js — the badge lives here.
//
// A module Worker so a runaway edit (accidental `while True:`) can never
// freeze the editor: the page pings us, and if Python starves the worker's
// event loop the page terminates + respawns the whole worker (~2 s reboot,
// last good code reloaded). Inside:
//
//   ctx.wasm   the badge's real C renderer (emfcamp firmware build),
//              instantiated natively with a ~40-line WASI shim
//   Pyodide    runs the official sim fakes + REAL firmware scheduler/eventbus
//   chost      the JS module Python talks to: raw wasm exports, string
//              helpers, canvas blits, LEDs, buttons, IMU, the virtual clock
//
// Frames are painted onto an OffscreenCanvas transferred from the page.

const post = (msg) => self.postMessage(msg);
const progress = (stage) => post({ type: "progress", stage });

// Injected by esbuild --define at build time; busts caches that ignore
// no-store (some proxies, some embedded browsers) whenever dist is rebuilt.
const BUILD = typeof __BUILD_ID__ === "string" ? __BUILD_ID__ : "dev";

// ---------------------------------------------------------------------------
// State shared with the Python side through `chost`
// ---------------------------------------------------------------------------
// pendingDown latches presses shorter than one Python poll interval (30 ms —
// a fast tap or a synthetic click would otherwise vanish between polls).
const input = { buttons: 0, pendingDown: 0, ax: 0, ay: 0 };
const vclock = { vms: 0, last: 0, speed: 1, paused: false };

function nowMs() {
  const n = performance.now();
  if (vclock.last === 0) vclock.last = n;
  if (!vclock.paused) vclock.vms += (n - vclock.last) * vclock.speed;
  vclock.last = n;
  return vclock.vms;
}

let screenCtx = null; // OffscreenCanvas 2d context
let frameCount = 0;
let lastFps = 0;

// ---------------------------------------------------------------------------
// ctx.wasm — minimal WASI shim (verified: only clock/environ ever called)
// ---------------------------------------------------------------------------
async function loadCtxWasm() {
  const resp = await fetchOk("./ctx.wasm");
  const bytes = await resp.arrayBuffer();

  let memory = null;
  const dv = () => new DataView(memory.buffer);
  const u8 = () => new Uint8Array(memory.buffer);
  const decoder = new TextDecoder();

  const wasi = {
    environ_sizes_get(countPtr, bufSizePtr) {
      dv().setUint32(countPtr, 0, true);
      dv().setUint32(bufSizePtr, 0, true);
      return 0;
    },
    environ_get() {
      return 0;
    },
    clock_time_get(...args) {
      // (i32 id, i64 precision, ptr out) — precision is a BigInt in browsers;
      // tolerate a legalized 4-arg (i32,i32,i32,i32) form too.
      const ptr = Number(args.length >= 4 ? args[3] : args[2]);
      dv().setBigUint64(ptr, BigInt(Date.now()) * 1000000n, true);
      return 0;
    },
    fd_write(fd, iovs, iovsLen, nwrittenPtr) {
      let written = 0;
      let out = "";
      for (let i = 0; i < iovsLen; i++) {
        const base = dv().getUint32(iovs + i * 8, true);
        const len = dv().getUint32(iovs + i * 8 + 4, true);
        out += decoder.decode(u8().subarray(base, base + len));
        written += len;
      }
      if (out) console.warn("[ctx.wasm]", out);
      dv().setUint32(nwrittenPtr, written, true);
      return 0;
    },
    fd_close() {
      return 0;
    },
    fd_seek(...args) {
      const ptr = Number(args[args.length - 1]);
      dv().setBigUint64(ptr, 0n, true);
      return 0;
    },
    proc_exit(code) {
      throw new Error(`ctx.wasm proc_exit(${code})`);
    },
  };

  const { instance } = await WebAssembly.instantiate(bytes, {
    wasi_snapshot_preview1: wasi,
  });
  memory = instance.exports.memory;
  instance.exports._initialize();
  return instance;
}

// ---------------------------------------------------------------------------
// chost — what Python sees as `import chost`
// ---------------------------------------------------------------------------
function makeChost(wasm, pyodideFS) {
  const e = wasm.exports;
  const mem = () => new Uint8Array(e.memory.buffer);
  const enc = new TextEncoder();
  const imageDataCache = new Map(); // fbPtr -> ImageData (memory can't grow)
  const pixelCache = new Map(); // path -> {img, iw, ih} decoded pixels in wasm heap

  function alloc(n) {
    const p = e.malloc(n);
    if (!p) throw new Error(`ctx.wasm out of memory (malloc(${n}))`);
    return p;
  }

  function writeCString(s) {
    const bytes = enc.encode(s);
    const p = alloc(bytes.length + 1);
    mem().set(bytes, p);
    mem()[p + bytes.length] = 0;
    return [p, bytes.length + 1];
  }

  function readCString(ptr, maxLen = 256) {
    const m = mem();
    let end = ptr;
    while (end < ptr + maxLen && m[end] !== 0) end++;
    return new TextDecoder().decode(m.subarray(ptr, end));
  }

  return {
    e,

    parse(ctxPtr, s) {
      const [p] = writeCString(s);
      e.ctx_parse(ctxPtr, p);
      e.free(p);
    },

    textWidth(ctxPtr, s) {
      const [p] = writeCString(s);
      const w = e.ctx_text_width(ctxPtr, p);
      e.free(p);
      return w;
    },

    defineTexture(ctxPtr, eid, w, h, stride, fmt, bufPtr) {
      const [p] = writeCString(eid);
      const retEid = alloc(65);
      e.ctx_define_texture(ctxPtr, p, w, h, stride, fmt, bufPtr, retEid);
      const actual = readCString(retEid, 65);
      e.free(retEid);
      e.free(p);
      return actual;
    },

    drawTexture(ctxPtr, eid, x, y, w, h) {
      const [p] = writeCString(eid);
      e.ctx_draw_texture(ctxPtr, p, x, y, w, h);
      e.free(p);
    },

    image(ctxPtr, path, x, y, w, h) {
      // Decode a MEMFS image via stb inside ctx.wasm, then draw it. Matches
      // upstream fakes/ctx.py image(): decoded PIXELS are cached, but the
      // texture is (re)defined on every call — textures are serialized into
      // the target drawlist, so caching the eid across drawlists (e.g. after
      // a probe frame that is destroyed unrendered) would blank the image.
      let px = pixelCache.get(path);
      if (!px) {
        const data = pyodideFS().readFile(path); // Uint8Array
        const buf = alloc(data.length);
        mem().set(data, buf);
        const wh = alloc(12);
        const img = e.stbi_load_from_memory(buf, data.length, wh, wh + 4, wh + 8, 4);
        const dvw = new DataView(e.memory.buffer);
        const iw = dvw.getUint32(wh, true);
        const ih = dvw.getUint32(wh + 4, true);
        e.free(wh);
        e.free(buf);
        if (!img) throw new Error(`stb could not decode ${path}`);
        px = { img, iw, ih };
        pixelCache.set(path, px);
      }
      const eid = this.defineTexture(
        ctxPtr, path, px.iw, px.ih, px.iw * 4, 4 /* RGBA8 */, px.img
      );
      const [p] = writeCString(eid);
      e.ctx_draw_texture(ctxPtr, p, x, y, w, h);
      e.free(p);
    },

    blit(fbPtr) {
      if (!screenCtx) return;
      let imgData = imageDataCache.get(fbPtr);
      if (!imgData) {
        const view = new Uint8ClampedArray(e.memory.buffer, fbPtr, 240 * 240 * 4);
        imgData = new ImageData(view, 240, 240);
        imageDataCache.set(fbPtr, imgData);
      }
      screenCtx.putImageData(imgData, 0, 0);
      frameCount++;
    },

    setLeds(csv) {
      const colors = csv
        .split(",")
        .map((s) => s.trim().split(/\s+/).map(Number));
      post({ type: "leds", colors });
    },

    buttons: () => {
      const bits = input.buttons | input.pendingDown;
      input.pendingDown = 0;
      return bits;
    },
    acc: (i) => (i === 0 ? input.ax : input.ay),
    nowMs,

    appError(json) {
      post({ type: "apperror", ...JSON.parse(json) });
    },
  };
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
let pyodide = null;
let swapFn = null;
let resetFn = null;
const preReadyQueue = [];

async function fetchOk(rel) {
  const url = new URL(`${rel}?b=${BUILD}`, self.location.href);
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} fetching ${url.pathname}`);
  return r;
}

async function boot() {
  progress("loading badge renderer (ctx.wasm)");
  const wasmPromise = loadCtxWasm();
  const treePromise = fetchOk("./badge-tree.zip").then((r) => r.arrayBuffer());
  const bootPyPromise = fetchOk("./boot.py").then((r) => r.text());

  progress("loading Python (Pyodide)");
  const { loadPyodide } = await import(
    new URL("./pyodide/pyodide.js", self.location.href).href
  );
  pyodide = await loadPyodide({
    indexURL: new URL("./pyodide/", self.location.href).href,
  });
  pyodide.setStdout({
    batched: (s) => post({ type: "print", text: s, stream: "out" }),
  });
  pyodide.setStderr({
    batched: (s) => post({ type: "print", text: s, stream: "err" }),
  });

  progress("unpacking badge firmware");
  const wasm = await wasmPromise;
  pyodide.FS.mkdirTree("/badge");
  pyodide.unpackArchive(new Uint8Array(await treePromise), "zip", {
    extractDir: "/badge",
  });

  pyodide.registerJsModule("chost", makeChost(wasm, () => pyodide.FS));

  progress("booting badge OS");
  await pyodide.runPythonAsync(await bootPyPromise);
  swapFn = pyodide.globals.get("swap_app");
  resetFn = pyodide.globals.get("reset_app");

  post({ type: "ready" });
  for (const m of preReadyQueue) handle(m);
  preReadyQueue.length = 0;

  setInterval(() => {
    lastFps = frameCount * 2;
    frameCount = 0;
    post({
      type: "stats",
      fps: lastFps,
      tSec: vclock.vms / 1000,
      paused: vclock.paused,
      speed: vclock.speed,
    });
  }, 500);
}

function doSwap(src, carry = true, id = null) {
  let ok = false;
  try {
    ok = swapFn(src, carry);
  } catch (err) {
    post({
      type: "apperror",
      kind: "swap",
      message: String(err.message || err).split("\n").slice(-3).join("\n"),
      line: null,
    });
  }
  post({ type: "swapped", ok, id });
}

function handle(msg) {
  switch (msg.type) {
    case "swap":
      doSwap(msg.src, msg.carry !== false, msg.id ?? null);
      break;
    case "reset":
      try {
        resetFn();
        post({ type: "swapped", ok: true, id: null });
      } catch (err) {
        console.error(err);
      }
      break;
    case "buttons":
      input.pendingDown |= msg.bits & ~input.buttons;
      input.buttons = msg.bits;
      break;
    case "acc":
      input.ax = msg.x;
      input.ay = msg.y;
      break;
    case "clock":
      nowMs(); // settle accumulated time under the old settings first
      if (msg.paused !== undefined) vclock.paused = msg.paused;
      if (msg.speed !== undefined) vclock.speed = msg.speed;
      break;
    case "step":
      vclock.vms += msg.ms || 50; // one badge frame
      break;
    case "capture":
      // Thumbnail for the gallery: a copy of the most recent blitted frame.
      // createImageBitmap (not transferToImageBitmap) so the visible canvas
      // keeps its frame; the bitmap transfers back zero-copy.
      if (!screenCtx) break;
      createImageBitmap(screenCtx.canvas)
        .then((bitmap) =>
          self.postMessage({ type: "captured", bitmap, id: msg.id ?? null }, [bitmap])
        )
        .catch(() => {});
      break;
    default:
      break;
  }
}

self.onmessage = (ev) => {
  const msg = ev.data;
  if (msg.type === "ping") {
    post({ type: "pong", id: msg.id });
    return;
  }
  if (msg.type === "init") {
    screenCtx = msg.canvas.getContext("2d");
    boot().catch((err) => {
      console.error(err);
      post({ type: "fatal", message: String(err.stack || err) });
    });
    return;
  }
  if (!swapFn && (msg.type === "swap" || msg.type === "reset")) {
    preReadyQueue.push(msg);
    return;
  }
  handle(msg);
};
