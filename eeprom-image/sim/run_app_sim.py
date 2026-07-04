#!/usr/bin/env python3
"""Run the UNMODIFIED badge app (../app.py) on a host PC and render what the
badge screen would show, so you can preview the logo without hardware.

    python3 sim/run_app_sim.py            # writes screen.png (or screen.ppm)
    python3 sim/run_app_sim.py --missing  # simulate a missing logo.dat

It fakes the badge's app/ctx/event modules, drives the app's update()/draw()
loop, and rasterizes the rectangles it draws into a 240x240 image. This checks
the app's logic and the logo.dat decoding; it says nothing about real badge
timing or colors.
"""
import argparse
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APPDIR = os.path.dirname(HERE)
APP = os.path.join(APPDIR, "app.py")


class FakeApp:
    def minimise(self):
        self.minimised = True


class FakeButtons:
    pressed = set()

    def __init__(self, app):
        pass

    def get(self, name):
        return name in FakeButtons.pressed

    def clear(self):
        FakeButtons.pressed.clear()


class FakeEventBus:
    def __init__(self):
        self.events = []

    def emit(self, e):
        self.events.append(e)


class RequestForegroundPushEvent:
    def __init__(self, app):
        self.app = app


class FakeCtx:
    """Rasterizes rgb().rectangle().fill() into a 240x240 RGB buffer; records
    text. Screen origin is the center, -120..120."""
    CENTER = "center"

    def __init__(self):
        self.fb = bytearray(240 * 240 * 3)
        self.font_size = 10
        self.text_align = None
        self._c = (0, 0, 0)
        self._r = None
        self.texts = []
        self.fills = 0

    def save(self):
        return self

    def restore(self):
        return self

    def rgb(self, r, g, b):
        for v in (r, g, b):
            assert -0.001 <= v <= 1.001, "ctx.rgb wants 0..1 floats, got %r" % v
        self._c = (r, g, b)
        return self

    def rectangle(self, x, y, w, h):
        self._r = (x, y, w, h)
        return self

    def fill(self):
        x, y, w, h = self._r
        r, g, b = [max(0, min(255, int(v * 255))) for v in self._c]
        x0 = int(x) + 120
        y0 = int(y) + 120
        for py in range(max(0, y0), min(240, y0 + int(round(h)))):
            base = py * 240 * 3
            for px in range(max(0, x0), min(240, x0 + int(round(w)))):
                o = base + px * 3
                self.fb[o] = r
                self.fb[o + 1] = g
                self.fb[o + 2] = b
        self.fills += 1
        return self

    def move_to(self, x, y):
        self._p = (x, y)
        return self

    def text(self, s):
        self.texts.append(s)
        return self


def save(ctx, path):
    try:
        from PIL import Image
        Image.frombytes("RGB", (240, 240), bytes(ctx.fb)).save(path)
        return path
    except ImportError:
        path = path.rsplit(".", 1)[0] + ".ppm"
        with open(path, "wb") as f:
            f.write(b"P6\n240 240\n255\n")
            f.write(bytes(ctx.fb))
        return path


def install_fakes():
    appmod = types.ModuleType("app")
    appmod.App = FakeApp
    sys.modules["app"] = appmod

    events = types.ModuleType("events")
    ei = types.ModuleType("events.input")
    ei.Buttons = FakeButtons
    ei.BUTTON_TYPES = {k: k for k in ("UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")}
    events.input = ei
    sys.modules["events"] = events
    sys.modules["events.input"] = ei

    bus = FakeEventBus()
    system = types.ModuleType("system")
    ebm = types.ModuleType("system.eventbus")
    ebm.eventbus = bus
    sch = types.ModuleType("system.scheduler")
    sev = types.ModuleType("system.scheduler.events")
    sev.RequestForegroundPushEvent = RequestForegroundPushEvent
    for name, mod in (("system", system), ("system.eventbus", ebm),
                      ("system.scheduler", sch), ("system.scheduler.events", sev)):
        sys.modules[name] = mod
    return bus


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--missing", action="store_true",
                    help="hide logo.dat to preview the load-failed screen")
    ap.add_argument("--out", default=os.path.join(APPDIR, "screen.png"))
    args = ap.parse_args()

    # the app finds logo.dat in the current directory when it has no slot
    os.chdir(APPDIR)
    if args.missing and os.path.exists("logo.dat"):
        os.rename("logo.dat", "logo.dat.hidden")

    bus = install_fakes()
    try:
        ns = {"__name__": "protogon_logo_sim"}
        exec(compile(open(APP).read(), APP, "exec"), ns)
        app = ns["__app_export__"](config=None)

        print("### LOGO APP SIMULATION -- fake badge, no hardware ###\n")
        drew = False
        for _ in range(6):
            r = app.update(50)
            if r is not False:
                ctx = FakeCtx()
                app.draw(ctx)
                drew = True
        out = save(ctx, args.out)

        # scripted CANCEL: app must clear the press and minimise
        FakeButtons.pressed.add("CANCEL")
        app.update(50)
        assert getattr(app, "minimised", False), "CANCEL did not minimise"
        assert not FakeButtons.pressed, "app must clear button state on minimise"
        fg = [e for e in bus.events if isinstance(e, RequestForegroundPushEvent)]
        assert len(fg) == 1, "expected one foreground request, got %d" % len(fg)

        assert drew, "app never drew"
        if args.missing:
            assert app.error is not None, "expected a load error with logo.dat missing"
            print("load-failed screen OK: error = %s" % app.error)
        else:
            assert app.spans, "logo.dat produced no white runs"
            white = sum(ctx.fb)
            assert white > 0, "screen is entirely black"
            print("logo OK: %dx%d, %d white runs, scale %dx, drawn with %d rects"
                  % (app.w, app.h, len(app.spans), app.scale, ctx.fills - 1))
        print("wrote %s" % out)
        print("\n### END SIMULATION -- logic only, not real badge output ###")
    finally:
        if os.path.exists("logo.dat.hidden"):
            os.rename("logo.dat.hidden", "logo.dat")


if __name__ == "__main__":
    main()
