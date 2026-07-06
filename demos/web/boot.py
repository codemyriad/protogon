# Playground bootstrap, run once inside Pyodide by sim-worker.js (after the
# badge tree is unpacked to /badge and the `chost` JS module is registered).
#
# This is the browser equivalent of the official sim's run.py: it arranges
# sys.path so the fakes shadow the stdlib, performs the same `time` reload
# dance, installs the MicroPython-only sys.print_exception, then boots the
# REAL badge OS (system.scheduler + system.eventbus from emfcamp firmware,
# unmodified) with the live-coded app as the only foreground app.
#
# It also owns the live-editing machinery:
#   swap_app(src)  compile+instantiate the edited source; if healthy, migrate
#                  scalar state from the running instance and swap it in via
#                  the scheduler's own start/stop events. If broken, report
#                  the error and leave the old app running (tixy.land rule:
#                  never interrupt the picture).
#   reset_app()    fresh instance, no state carry-over.
#
# Errors -- both swap failures and runtime crashes the scheduler catches --
# are routed to chost.appError() as JSON {kind, message, line} so the editor
# can pin a diagnostic to the offending line.

import importlib
import json
import sys
import traceback

import chost

BOOT_REV = 5
print(f"boot.py rev {BOOT_REV}")

LIVE_FILE = "/live/app.py"

# --- sys.path + time shadowing (mirrors sim/run.py) -------------------------

sys.modules.setdefault("_time", __import__("time"))

# Fakes shadow the stdlib (time, gc), modules is the real firmware.
sys.path = ["/badge/fakes", "/badge/modules", "/badge/modules/lib"] + [
    p for p in sys.path if not p.startswith("/badge/")
]

# importlib.reload() re-finds the module spec through sys.meta_path, so the
# sys.path-based finder must come before BuiltinImporter or reload(time) just
# re-initialises the C module. Reorder rather than replace (upstream run.py
# replaces the whole list, which would break Pyodide's JS finder).
from importlib.machinery import PathFinder

if PathFinder in sys.meta_path:
    sys.meta_path.remove(PathFinder)
    sys.meta_path.insert(0, PathFinder)
importlib.invalidate_caches()

import time

importlib.reload(time)  # exec fakes/time.py into the stdlib module (adds ticks_*)
sys.modules["time"] = time
assert hasattr(time, "ticks_us"), "fakes/time.py did not shadow the stdlib"

import os

os.makedirs("/flash", exist_ok=True)
os.makedirs("/live", exist_ok=True)


def _report(kind, exc):
    """Send an exception to the editor with the line number of the deepest
    frame that lives in the live-edited file."""
    line = None
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename == LIVE_FILE:
            line = frame.lineno
    if line is None and isinstance(exc, SyntaxError) and exc.filename == LIVE_FILE:
        line = exc.lineno
    message = "".join(traceback.format_exception_only(exc)).strip()
    chost.appError(json.dumps({"kind": kind, "message": message, "line": line}))
    print(f"[{kind}] {message}", file=sys.stderr)


def _print_exception(exc, file=None):
    # MicroPython API the scheduler/eventbus call whenever an app crashes.
    traceback.print_exception(exc, file=file or sys.stderr)
    _report("crash", exc)


sys.print_exception = _print_exception

# --- boot the badge OS -------------------------------------------------------

import asyncio

# The scheduler package must be imported before anything that pulls in
# system.eventbus (eventbus <-> scheduler are circular; firmware main.py
# resolves the cycle by importing the scheduler first).
from system.scheduler import scheduler
from system.scheduler.events import RequestStartAppEvent, RequestStopAppEvent
from system.eventbus import eventbus
from events.input import BUTTON_TYPES, ButtonDownEvent, ButtonUpEvent

scheduler.a11y_handler = None  # no espeak in a browser; keeps draw loop quiet

# Physical buttons A..F (top, clockwise) -> logical System buttons, same
# mapping as modules/frontboards/twentyfour.py.
_BUTTON_ORDER = ("UP", "RIGHT", "CONFIRM", "DOWN", "LEFT", "CANCEL")


async def _input_pump():
    """Poll the JS-owned button bitmask and turn edges into the same
    ButtonDown/ButtonUp events the 2024 frontboard emits on hardware."""
    prev = 0
    while True:
        bits = int(chost.buttons())
        changed = bits ^ prev
        if changed:
            for i, name in enumerate(_BUTTON_ORDER):
                if changed & (1 << i):
                    ev = (ButtonDownEvent if bits & (1 << i) else ButtonUpEvent)(
                        button=BUTTON_TYPES[name]
                    )
                    eventbus.emit(ev)
            prev = bits
        await asyncio.sleep(0.03)


_state = {"app": None, "task": None}


def _instantiate(src):
    ns = {"__name__": "__live__", "__file__": LIVE_FILE}
    code = compile(src, LIVE_FILE, "exec")
    exec(code, ns)
    cls = ns.get("__app_export__")
    if cls is None:
        import app as _appmod

        for v in ns.values():
            if (
                isinstance(v, type)
                and issubclass(v, _appmod.App)
                and v is not _appmod.App
            ):
                cls = v
    if cls is None:
        raise RuntimeError("No __app_export__ (or app.App subclass) found")
    try:
        return cls(config=None)
    except TypeError:
        return cls()


_CARRY_TYPES = (int, float, bool, str)


def _carry_state(old, new):
    """Migrate evolving scalar state (t, mode, speed, ...) from the running
    instance so an edit changes behaviour without restarting the animation.
    Containers are NOT copied: they are usually derived from module constants
    the edit may have just changed. An app can override the heuristic by
    defining __live_state__ = ("attr", ...)."""
    names = getattr(new, "__live_state__", None)
    if names is None:
        names = [
            k
            for k, v in old.__dict__.items()
            if k in new.__dict__
            and isinstance(v, _CARRY_TYPES)
            and isinstance(new.__dict__[k], _CARRY_TYPES)
        ]
    for k in names:
        if k in old.__dict__:
            try:
                new.__dict__[k] = old.__dict__[k]
            except Exception:
                pass


def _probe(app_instance):
    """Run one hidden update+draw against a throwaway drawlist so runtime
    errors (not just syntax errors) reject a swap BEFORE the old app is
    stopped. The probe never touches the screen."""
    import ctx as _ctx

    dctx = _ctx._wasm.ctx_new_drawlist(240, 240)
    print("[probe] start")
    try:
        app_instance.update(0)
        app_instance.draw(_ctx.Context(dctx))
        print("[probe] passed")
    finally:
        _ctx._wasm.ctx_destroy(dctx)


def swap_app(src, carry=True):
    """Called (synchronously, via a PyProxy) by the worker on every edit.
    Returns True if the new code took over, False if the old app kept running."""
    old = _state["app"]
    new = None
    try:
        with open(LIVE_FILE, "w") as f:
            f.write(src)
        new = _instantiate(src)
        if old is not None and carry:
            _carry_state(old, new)
        _probe(new)
    except Exception as e:
        _report("swap", e)
        if new is not None:  # drop Buttons handlers the failed instance registered
            eventbus.deregister(new)
        return False

    if old is not None:
        eventbus.emit(RequestStopAppEvent(app=old))
    eventbus.emit(RequestStartAppEvent(new, foreground=True))
    _state["app"] = new
    return True


def reset_app():
    """Fresh instance of the current code, no state carry-over."""
    try:
        with open(LIVE_FILE) as f:
            src = f.read()
    except OSError:
        return False
    return swap_app(src, carry=False)


def boot():
    if _state["task"] is not None:
        return
    _state["task"] = asyncio.ensure_future(scheduler._main())

    def _crashed(task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _report("fatal", exc)

    _state["task"].add_done_callback(_crashed)
    asyncio.ensure_future(_input_pump())


boot()
