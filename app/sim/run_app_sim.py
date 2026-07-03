#!/usr/bin/env python3
"""Run the UNMODIFIED badge app (app/app.py) on a host PC, no badge needed.

It reuses the diagnostics' fake hardware (fake I2C bus + animated MLX90640 on
a virtual clock), adds fakes for the badge's app/ctx/event APIs, drives the
app's update()/draw() loop, and rasterizes every draw into an image file --
so you can SEE what the badge screen will show before you own the hardware.

    python3 run_app_sim.py                  # writes thermal_000.png/.ppm ...
    python3 run_app_sim.py --no-camera      # the "check the Qwiic cable" screen
    python3 run_app_sim.py --steps 1000     # a longer run, more frames

Like the diagnostics sim, this validates LOGIC only: real timing, colors and
badge quirks need the actual badge.
"""
import argparse
import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app.py")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)),
                                "diagnostics", "sim"))
import fakehw  # noqa: E402


# ---------------------------------------------------------------- badge fakes
class FakeAppBase:
    def minimise(self):
        self.minimised = True


class FakeButtons:
    pressed = set()          # scripted by the runner, cleared by the app

    def __init__(self, app):
        pass

    def get(self, name):
        return name in FakeButtons.pressed

    def clear(self):
        FakeButtons.pressed.clear()


class FakeEventBus:
    def __init__(self):
        self.emitted = []

    def emit(self, event):
        self.emitted.append(event)


class RequestForegroundPushEvent:
    def __init__(self, app):
        self.app = app


class FakeCtx:
    """Records draw calls and rasterizes rectangle fills into a 240x240 RGB
    framebuffer (the badge's round screen, origin at the center)."""
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"

    def __init__(self):
        self.fb = bytearray(240 * 240 * 3)
        self.font_size = 10
        self.text_align = None
        self._color = (0, 0, 0)
        self._rect = None
        self.rect_fills = 0
        self.texts = []          # (x, y, string)

    def save(self):
        return self

    def restore(self):
        return self

    def rgb(self, r, g, b):
        for v in (r, g, b):
            assert -0.001 <= v <= 1.001, "ctx.rgb wants 0..1 floats, got %r" % v
        self._color = (r, g, b)
        return self

    def rectangle(self, x, y, w, h):
        self._rect = (x, y, w, h)
        return self

    def fill(self):
        x, y, w, h = self._rect
        assert -120.001 <= x and x + w <= 120.001, "rect x off-screen: %r" % (self._rect,)
        assert -120.001 <= y and y + h <= 120.001, "rect y off-screen: %r" % (self._rect,)
        r, g, b = [max(0, min(255, int(v * 255))) for v in self._color]
        for py in range(int(y) + 120, int(y + h) + 120):
            row = py * 240 * 3
            for px in range(int(x) + 120, int(x + w) + 120):
                o = row + px * 3
                self.fb[o] = r
                self.fb[o + 1] = g
                self.fb[o + 2] = b
        self.rect_fills += 1
        return self

    def move_to(self, x, y):
        self._pos = (x, y)
        return self

    def text(self, s):
        self.texts.append((self._pos[0], self._pos[1], s))
        return self


def save_image(ctx, path):
    try:
        from PIL import Image
        img = Image.frombytes("RGB", (240, 240), bytes(ctx.fb))
        img.save(path)
        return path
    except ImportError:
        path = path.rsplit(".", 1)[0] + ".ppm"
        with open(path, "wb") as f:
            f.write(b"P6\n240 240\n255\n")
            f.write(bytes(ctx.fb))
        return path


def install_fakes(clock, faults, no_camera):
    buses = {}

    def get_bus(port):
        if port not in buses:
            buses[port] = fakehw.FakeI2C(port, clock, faults)
            if no_camera:
                buses[port].scan = lambda: [fakehw.EEPROM_ADDR]
        return buses[port]

    machine = types.ModuleType("machine")
    machine.I2C = get_bus
    sys.modules["machine"] = machine

    appmod = types.ModuleType("app")
    appmod.App = FakeAppBase
    sys.modules["app"] = appmod

    events = types.ModuleType("events")
    events_input = types.ModuleType("events.input")
    events_input.Buttons = FakeButtons
    events_input.BUTTON_TYPES = {k: k for k in
                                 ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")}
    events.input = events_input
    sys.modules["events"] = events
    sys.modules["events.input"] = events_input

    bus = FakeEventBus()
    system = types.ModuleType("system")
    eventbus_mod = types.ModuleType("system.eventbus")
    eventbus_mod.eventbus = bus
    sched = types.ModuleType("system.scheduler")
    sched_events = types.ModuleType("system.scheduler.events")
    sched_events.RequestForegroundPushEvent = RequestForegroundPushEvent
    for name, mod in (("system", system), ("system.eventbus", eventbus_mod),
                      ("system.scheduler", sched), ("system.scheduler.events", sched_events)):
        sys.modules[name] = mod
    return bus


def main():
    ap = argparse.ArgumentParser(description="Run the Protogon thermal app on fake hardware.")
    ap.add_argument("--steps", type=int, default=400,
                    help="update() calls to simulate (50 virtual ms each)")
    ap.add_argument("--port", type=int, default=0,
                    help="pass a HexpansionConfig with this port (0 = no config, "
                         "the app scans all slots itself)")
    ap.add_argument("--no-camera", action="store_true",
                    help="simulate a missing camera to see the help screen")
    ap.add_argument("--max-frames", type=int, default=4, help="images to write")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    clock = fakehw.VClock()
    faults = fakehw.Faults()
    bus = install_fakes(clock, faults, args.no_camera)

    ns = {"__name__": "protogon_app_sim"}
    exec(compile(open(APP).read(), APP, "exec"), ns)
    config = types.SimpleNamespace(port=args.port) if args.port else None
    app = ns["__app_export__"](config=config)

    print("### APP SIMULATION -- fake badge + fake camera, virtual clock ###\n")
    draws = 0
    thermal_draws = 0
    frames_saved = 0
    for step in range(args.steps):
        redraw = app.update(50)
        clock.advance(50)
        if not redraw:
            continue
        draws += 1
        ctx = FakeCtx()
        app.draw(ctx)
        if app.levels:
            thermal_draws += 1
        if app.levels and frames_saved < args.max_frames:
            path = os.path.join(args.outdir, "thermal_%03d.png" % frames_saved)
            path = save_image(ctx, path)
            print("step %4d: thermal frame -> %s  (%d rect fills, scale %d..%d)"
                  % (step, path, ctx.rect_fills, app.lo, app.hi))
            frames_saved += 1
        elif not app.levels:
            print("step %4d: message screen: %r" % (step, app.msg.replace("\n", " / ")))

    # scripted CANCEL press: the app must clear the press and minimise
    FakeButtons.pressed.add("CANCEL")
    app.update(50)
    assert getattr(app, "minimised", False), "CANCEL did not minimise the app"
    assert not FakeButtons.pressed, "the app must clear button state on minimise"

    fg = [e for e in bus.emitted if isinstance(e, RequestForegroundPushEvent)]
    assert len(fg) == 1, "expected exactly one RequestForegroundPushEvent, got %d" % len(fg)

    print("\n%d update() calls -> %d redraws (the app skips redundant redraws)"
          % (args.steps, draws))
    if args.no_camera:
        assert app.levels is None and "no camera" in app.msg
        print("no-camera path OK: app shows %r and keeps rescanning" % app.msg.split("\n")[0])
    else:
        assert thermal_draws > 0, "no thermal frame was ever drawn"
        print("thermal path OK: foregrounded once, CANCEL minimises, "
              "%d thermal draws, %d frames saved" % (thermal_draws, frames_saved))
    print("\n### END APP SIMULATION -- logic only, not badge timing/colors ###")


if __name__ == "__main__":
    main()
