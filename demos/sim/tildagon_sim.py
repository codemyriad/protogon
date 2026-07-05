# Tildagon badge host-simulator: run an UNMODIFIED badge app on a plain PC.
#
# The EMF Tildagon badge runs MicroPython apps built around update(delta) /
# draw(ctx) on a round 240x240 screen (origin at the centre, coords -120..120)
# with six buttons, an IMU and a ring of RGB LEDs. This module fakes just
# enough of that runtime -- the `ctx` canvas, the `app`/`events`/`system`
# modules, a scripted IMU and the LED ring -- and rasterises every draw() into
# a PPM image, so you can SEE a demo before touching hardware.
#
# It is pure standard-library Python (no PIL/numpy/SDL): frames are written as
# binary PPM (P6); run.py stitches them into a GIF with ffmpeg. Like every host
# sim it validates LOGIC and COMPOSITION only -- real colours, timing and the
# on-glass round crop still need the badge (or the official SDL2 simulator).
#
# The rasteriser is a small scan-line filler + coverage-based stroker with an
# affine transform stack, so ctx.rotate/translate/scale, translucent fills and
# thin strokes all render the way the demos expect.

import math
import os
import struct
import sys
import types

SIZE = 240                      # badge framebuffer is 240x240
CENTER = SIZE / 2.0
NUM_LEDS = 12                   # documented app/pattern LED target


# --------------------------------------------------------------------------- #
#  A tiny 5x7 bitmap font (enough for labels + Matrix-rain glyphs).           #
#  Each glyph is 7 rows of 5 columns; 'X' = lit pixel. Unknown chars fall     #
#  back to a solid block so text still reads as "something is there".         #
# --------------------------------------------------------------------------- #
_FONT_SRC = {
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    ".": ("     ", "     ", "     ", "     ", "     ", " XX  ", " XX  "),
    ":": ("     ", " XX  ", " XX  ", "     ", " XX  ", " XX  ", "     "),
    "-": ("     ", "     ", "     ", "XXXXX", "     ", "     ", "     "),
    "+": ("     ", "  X  ", "  X  ", "XXXXX", "  X  ", "  X  ", "     "),
    "*": ("     ", "X X X", " XXX ", "XXXXX", " XXX ", "X X X", "     "),
    "/": ("    X", "    X", "   X ", "  X  ", " X   ", "X    ", "X    "),
    "=": ("     ", "     ", "XXXXX", "     ", "XXXXX", "     ", "     "),
    "!": ("  X  ", "  X  ", "  X  ", "  X  ", "  X  ", "     ", "  X  "),
    "#": (" X X ", " X X ", "XXXXX", " X X ", "XXXXX", " X X ", " X X "),
    "%": ("XX  X", "XX X ", "  X  ", " X X ", "X XX ", "X  XX", "     "),
    "<": ("   X ", "  X  ", " X   ", "X    ", " X   ", "  X  ", "   X "),
    ">": (" X   ", "  X  ", "   X ", "    X", "   X ", "  X  ", " X   "),
    "?": (" XXX ", "X   X", "    X", "   X ", "  X  ", "     ", "  X  "),
    "@": (" XXX ", "X   X", "X XXX", "X X X", "X XXX", "X    ", " XXX "),
    "0": (" XXX ", "X   X", "X  XX", "X X X", "XX  X", "X   X", " XXX "),
    "1": ("  X  ", " XX  ", "  X  ", "  X  ", "  X  ", "  X  ", " XXX "),
    "2": (" XXX ", "X   X", "    X", "   X ", "  X  ", " X   ", "XXXXX"),
    "3": ("XXXXX", "   X ", "  X  ", "   X ", "    X", "X   X", " XXX "),
    "4": ("   X ", "  XX ", " X X ", "X  X ", "XXXXX", "   X ", "   X "),
    "5": ("XXXXX", "X    ", "XXXX ", "    X", "    X", "X   X", " XXX "),
    "6": ("  XX ", " X   ", "X    ", "XXXX ", "X   X", "X   X", " XXX "),
    "7": ("XXXXX", "    X", "   X ", "  X  ", " X   ", " X   ", " X   "),
    "8": (" XXX ", "X   X", "X   X", " XXX ", "X   X", "X   X", " XXX "),
    "9": (" XXX ", "X   X", "X   X", " XXXX", "    X", "   X ", " XX  "),
    "A": (" XXX ", "X   X", "X   X", "XXXXX", "X   X", "X   X", "X   X"),
    "B": ("XXXX ", "X   X", "X   X", "XXXX ", "X   X", "X   X", "XXXX "),
    "C": (" XXX ", "X   X", "X    ", "X    ", "X    ", "X   X", " XXX "),
    "D": ("XXX  ", "X  X ", "X   X", "X   X", "X   X", "X  X ", "XXX  "),
    "E": ("XXXXX", "X    ", "X    ", "XXXX ", "X    ", "X    ", "XXXXX"),
    "F": ("XXXXX", "X    ", "X    ", "XXXX ", "X    ", "X    ", "X    "),
    "G": (" XXX ", "X   X", "X    ", "X XXX", "X   X", "X   X", " XXXX"),
    "H": ("X   X", "X   X", "X   X", "XXXXX", "X   X", "X   X", "X   X"),
    "I": (" XXX ", "  X  ", "  X  ", "  X  ", "  X  ", "  X  ", " XXX "),
    "J": ("  XXX", "   X ", "   X ", "   X ", "X  X ", "X  X ", " XX  "),
    "K": ("X   X", "X  X ", "X X  ", "XX   ", "X X  ", "X  X ", "X   X"),
    "L": ("X    ", "X    ", "X    ", "X    ", "X    ", "X    ", "XXXXX"),
    "M": ("X   X", "XX XX", "X X X", "X X X", "X   X", "X   X", "X   X"),
    "N": ("X   X", "XX  X", "X X X", "X X X", "X X X", "X  XX", "X   X"),
    "O": (" XXX ", "X   X", "X   X", "X   X", "X   X", "X   X", " XXX "),
    "P": ("XXXX ", "X   X", "X   X", "XXXX ", "X    ", "X    ", "X    "),
    "Q": (" XXX ", "X   X", "X   X", "X   X", "X X X", "X  X ", " XX X"),
    "R": ("XXXX ", "X   X", "X   X", "XXXX ", "X X  ", "X  X ", "X   X"),
    "S": (" XXXX", "X    ", "X    ", " XXX ", "    X", "    X", "XXXX "),
    "T": ("XXXXX", "  X  ", "  X  ", "  X  ", "  X  ", "  X  ", "  X  "),
    "U": ("X   X", "X   X", "X   X", "X   X", "X   X", "X   X", " XXX "),
    "V": ("X   X", "X   X", "X   X", "X   X", "X   X", " X X ", "  X  "),
    "W": ("X   X", "X   X", "X   X", "X X X", "X X X", "XX XX", "X   X"),
    "X": ("X   X", "X   X", " X X ", "  X  ", " X X ", "X   X", "X   X"),
    "Y": ("X   X", "X   X", " X X ", "  X  ", "  X  ", "  X  ", "  X  "),
    "Z": ("XXXXX", "    X", "   X ", "  X  ", " X   ", "X    ", "XXXXX"),
}


def _compile_font():
    out = {}
    for ch, rows in _FONT_SRC.items():
        bits = []
        for row in rows:
            bits.append([1 if c == "X" else 0 for c in row.ljust(5)[:5]])
        out[ch] = bits
    return out


_FONT = _compile_font()
_BLOCK = [[1] * 5 for _ in range(7)]


# --------------------------------------------------------------------------- #
#  The fake ctx canvas + software rasteriser.                                 #
# --------------------------------------------------------------------------- #
class Ctx:
    """A software rasteriser exposing the subset of the badge `ctx` API the
    demos use. Coordinates are centred (origin at the middle of the screen);
    fill/stroke honour the affine transform stack (rotate/translate/scale) and
    alpha, so the PPM output looks like the real draw."""

    # text-align constants (match the badge ctx attribute names)
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"
    START = "start"
    END = "end"
    TOP = "top"
    BOTTOM = "bottom"

    def __init__(self, size=SIZE):
        self.size = size
        self.fb = bytearray(size * size * 3)   # persistent framebuffer (black)
        self._m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self._stack = []
        self._subpaths = []       # each: [ (px,py), ... ] in device pixels
        self._cur = None
        self._color = (0.0, 0.0, 0.0)
        self._alpha = 1.0
        self.global_alpha = 1.0
        self.line_width = 1.0
        self.font_size = 10.0
        self.text_align = self.START
        self.text_baseline = self.MIDDLE
        # cheap instrumentation the runner/tests can assert on
        self.fill_count = 0
        self.stroke_count = 0
        self.text_count = 0

    # ---- transform stack -------------------------------------------------- #
    def save(self):
        self._stack.append((self._m, self._color, self._alpha,
                            self.line_width, self.font_size,
                            self.text_align, self.global_alpha))
        return self

    def restore(self):
        if self._stack:
            (self._m, self._color, self._alpha, self.line_width,
             self.font_size, self.text_align, self.global_alpha) = self._stack.pop()
        return self

    @staticmethod
    def _mul(m, n):
        ma, mb, mc, md, me, mf = m
        na, nb, nc, nd, ne, nf = n
        return (ma * na + mc * nb,
                mb * na + md * nb,
                ma * nc + mc * nd,
                mb * nc + md * nd,
                ma * ne + mc * nf + me,
                mb * ne + md * nf + mf)

    def translate(self, x, y):
        self._m = self._mul(self._m, (1.0, 0.0, 0.0, 1.0, x, y))
        return self

    def rotate(self, a):
        c, s = math.cos(a), math.sin(a)
        self._m = self._mul(self._m, (c, s, -s, c, 0.0, 0.0))
        return self

    def scale(self, sx, sy=None):
        if sy is None:
            sy = sx
        self._m = self._mul(self._m, (sx, 0.0, 0.0, sy, 0.0, 0.0))
        return self

    def _pt(self, x, y):
        a, b, c, d, e, f = self._m
        return (a * x + c * y + e + CENTER, b * x + d * y + f + CENTER)

    def _avg_scale(self):
        a, b, c, d, _, _ = self._m
        return (math.hypot(a, b) + math.hypot(c, d)) / 2.0

    # ---- colour ----------------------------------------------------------- #
    def rgb(self, r, g, b):
        self._color = (r, g, b)
        self._alpha = 1.0
        return self

    def rgba(self, r, g, b, a):
        self._color = (r, g, b)
        self._alpha = a
        return self

    def gray(self, v):
        self._color = (v, v, v)
        self._alpha = 1.0
        return self

    # ---- path building ---------------------------------------------------- #
    def begin_path(self):
        self._subpaths = []
        self._cur = None
        return self

    def move_to(self, x, y):
        self._cur = [self._pt(x, y)]
        self._subpaths.append(self._cur)
        return self

    def line_to(self, x, y):
        if self._cur is None:
            return self.move_to(x, y)
        self._cur.append(self._pt(x, y))
        return self

    def rel_line_to(self, dx, dy):
        # not transform-correct for rotation, but demos only use it un-rotated
        if self._cur is None:
            return self.move_to(dx, dy)
        lx, ly = self._cur[-1]
        self._cur.append((lx + dx * self._avg_scale(), ly + dy * self._avg_scale()))
        return self

    def rectangle(self, x, y, w, h):
        self._cur = [self._pt(x, y), self._pt(x + w, y),
                     self._pt(x + w, y + h), self._pt(x, y + h)]
        self._subpaths.append(self._cur)
        return self

    rect = rectangle

    def round_rectangle(self, x, y, w, h, r):
        return self.rectangle(x, y, w, h)   # good enough for previews

    def arc(self, x, y, r, a0, a1, ccw=False):
        # flatten to a polyline; connects from the current point like canvas.
        # The badge community idiom for a whole circle is arc(x,y,r,0,6.283,True)
        # -- i.e. a near-2*pi sweep with the direction flag set -- so treat any
        # near-full sweep as a full circle regardless of the flag.
        span = a1 - a0
        if abs(span) >= 2 * math.pi - 0.02:
            span = 2 * math.pi
        elif ccw and span > 0:
            span -= 2 * math.pi
        elif (not ccw) and span < 0:
            span += 2 * math.pi
        n = max(8, int(abs(span) / (2 * math.pi) * max(16, r * 1.6)))
        if self._cur is None:
            self._cur = []
            self._subpaths.append(self._cur)
        for i in range(n + 1):
            a = a0 + span * (i / n)
            self._cur.append(self._pt(x + r * math.cos(a), y + r * math.sin(a)))
        return self

    def quad_to(self, cx, cy, x, y):
        # flatten a quadratic Bezier from the current point (affine-safe: we
        # interpolate in device space, which an affine transform preserves)
        if self._cur is None:
            return self.move_to(x, y)
        x0, y0 = self._cur[-1]
        c = self._pt(cx, cy)
        p = self._pt(x, y)
        n = 14
        for i in range(1, n + 1):
            t = i / n
            mt = 1.0 - t
            self._cur.append((mt * mt * x0 + 2 * mt * t * c[0] + t * t * p[0],
                              mt * mt * y0 + 2 * mt * t * c[1] + t * t * p[1]))
        return self

    def curve_to(self, ax, ay, bx, by, x, y):
        if self._cur is None:
            self.move_to(ax, ay)
        x0, y0 = self._cur[-1]
        a = self._pt(ax, ay)
        b = self._pt(bx, by)
        p = self._pt(x, y)
        n = 18
        for i in range(1, n + 1):
            t = i / n
            mt = 1.0 - t
            self._cur.append((
                mt**3 * x0 + 3 * mt*mt*t * a[0] + 3 * mt*t*t * b[0] + t**3 * p[0],
                mt**3 * y0 + 3 * mt*mt*t * a[1] + 3 * mt*t*t * b[1] + t**3 * p[1]))
        return self

    def close_path(self):
        if self._cur and len(self._cur) > 1:
            self._cur.append(self._cur[0])
        return self

    # ---- paint ------------------------------------------------------------ #
    def _rgb255(self):
        r, g, b = self._color
        return (max(0, min(255, int(r * 255 + 0.5))),
                max(0, min(255, int(g * 255 + 0.5))),
                max(0, min(255, int(b * 255 + 0.5))))

    def _eff_alpha(self):
        return max(0.0, min(1.0, self._alpha * self.global_alpha))

    def _blend(self, x, y, r, g, b, a):
        if a <= 0.0 or not (0 <= x < self.size and 0 <= y < self.size):
            return
        if a >= 1.0:
            o = (y * self.size + x) * 3
            self.fb[o] = r
            self.fb[o + 1] = g
            self.fb[o + 2] = b
            return
        o = (y * self.size + x) * 3
        ia = 1.0 - a
        self.fb[o] = int(r * a + self.fb[o] * ia)
        self.fb[o + 1] = int(g * a + self.fb[o + 1] * ia)
        self.fb[o + 2] = int(b * a + self.fb[o + 2] * ia)

    def fill(self):
        r, g, b = self._rgb255()
        a = self._eff_alpha()
        for sp in self._subpaths:
            self._fill_poly(sp, r, g, b, a)
        self.fill_count += 1
        self._subpaths = []
        self._cur = None
        return self

    def _fill_poly(self, pts, r, g, b, a):
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.floor(min(ys))))
        y1 = min(self.size - 1, int(math.ceil(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x1, yy1 = pts[i]
                x2, yy2 = pts[(i + 1) % n]
                if (yy1 <= yc < yy2) or (yy2 <= yc < yy1):
                    t = (yc - yy1) / (yy2 - yy1)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                xa = int(math.ceil(xs[i] - 0.5))
                xb = int(math.floor(xs[i + 1] - 0.5))
                for x in range(max(0, xa), min(self.size - 1, xb) + 1):
                    self._blend(x, y, r, g, b, a)

    def stroke(self):
        r, g, b = self._rgb255()
        a = self._eff_alpha()
        w = max(self.line_width * self._avg_scale(), 0.9)
        rad = w / 2.0
        # accumulate coverage first, so a translucent stroke does not
        # over-darken where its own stamps overlap
        cov = {}
        for sp in self._subpaths:
            self._stroke_cov(cov, sp, rad)
        for (x, y), c in cov.items():
            self._blend(x, y, r, g, b, a * (c if c < 1.0 else 1.0))
        self.stroke_count += 1
        self._subpaths = []
        self._cur = None
        return self

    def _stroke_cov(self, cov, pts, rad):
        if len(pts) < 2:
            if pts:
                self._stamp(cov, pts[0][0], pts[0][1], rad)
            return
        step = max(0.5, rad * 0.8)
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            m = max(1, int(length / step))
            for s in range(m + 1):
                t = s / m
                self._stamp(cov, x1 + dx * t, y1 + dy * t, rad)

    def _stamp(self, cov, cx, cy, rad):
        if rad <= 0.75:
            cov[(int(cx), int(cy))] = 1.0
            return
        r2 = rad * rad
        x0 = max(0, int(cx - rad))
        x1 = min(self.size - 1, int(cx + rad))
        y0 = max(0, int(cy - rad))
        y1 = min(self.size - 1, int(cy + rad))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                    cov[(x, y)] = 1.0

    # ---- text ------------------------------------------------------------- #
    def text(self, s):
        r, g, b = self._rgb255()
        a = self._eff_alpha()
        px = int(self._scale_px(self.font_size) / 7.0)   # pixel size per cell
        px = max(1, px)
        gw = 6 * px           # 5 cols + 1 spacing
        total = gw * len(s)
        x0, y0 = self._cur[-1] if self._cur else self._pt(0, 0)
        if self.text_align in (self.CENTER, self.MIDDLE):
            x0 -= total / 2.0
        elif self.text_align in (self.RIGHT, self.END):
            x0 -= total
        y0 -= 3.5 * px        # vertically centre the 7-row glyph on the pen
        for ch in s:
            glyph = _FONT.get(ch.upper(), _BLOCK)
            for ry in range(7):
                for rx in range(5):
                    if glyph[ry][rx]:
                        bx = int(x0 + rx * px)
                        by = int(y0 + ry * px)
                        for yy in range(by, by + px):
                            for xx in range(bx, bx + px):
                                self._blend(xx, yy, r, g, b, a)
            x0 += gw
        self.text_count += 1
        return self

    def _scale_px(self, v):
        return v * self._avg_scale()

    # ctx has a few no-op-ish niceties demos may call
    def clip(self):
        self._subpaths = []
        self._cur = None
        return self

    def image(self, *a, **k):
        return self


# --------------------------------------------------------------------------- #
#  Fake badge runtime modules (app / events / system / tildagonos / imu).     #
# --------------------------------------------------------------------------- #
class FakeApp:
    def __init__(self, *a, **k):
        self.overlays = []          # real app.App.__init__ sets this

    def minimise(self):
        self.minimised = True

    def draw_overlays(self, ctx):   # no-op stand-in for the base hook
        pass

    def add_overlay(self, o):
        self.overlays.append(o)

    def remove_overlay(self, o):
        if o in self.overlays:
            self.overlays.remove(o)

    def _cleanup(self):
        pass


class Buttons:
    """Scripted by the runner via the shared `pressed` set; apps read .get()
    and clear it with .clear() exactly like the real events.input.Buttons."""
    pressed = set()

    def __init__(self, app):
        self.app = app

    def get(self, name):
        return name in Buttons.pressed

    def clear(self):
        Buttons.pressed.clear()


BUTTON_TYPES = {k: k for k in
                ("UNDEFINED", "UP", "DOWN", "LEFT", "RIGHT", "CONFIRM", "CANCEL")}


# LED ownership handshake (system.patterndisplay.events). Direct LED writes are
# overwritten by the pattern service unless an app emits PatternDisable() first
# and PatternEnable() when it leaves; the sim just records them on the bus.
class PatternDisable:
    pass


class PatternEnable:
    pass


class PatternReload:
    pass


class PatternSet:
    def __init__(self, pattern_class):
        self.pattern_class = pattern_class


class _EventBus:
    def __init__(self):
        self.emitted = []

    def emit(self, event):
        self.emitted.append(event)

    def emit_async(self, event):
        self.emitted.append(event)

    def on(self, *a, **k):
        pass

    def on_async(self, *a, **k):
        pass

    def remove(self, *a, **k):
        pass


class RequestForegroundPushEvent:
    def __init__(self, app):
        self.app = app


class RequestForegroundPopEvent:
    def __init__(self, app):
        self.app = app


class HexpansionConfig:
    def __init__(self, port):
        self.port = port


class _Leds:
    """Mimics tildagonos.leds: index 1..NUM_LEDS assignment of (r,g,b) 0..255
    tuples, plus .write(). (The real chain is 1-indexed.)"""
    def __init__(self, n):
        self.n = n
        self.state = [(0, 0, 0) for _ in range(n + 1)]   # 1-indexed

    def __setitem__(self, i, rgb):
        if 1 <= i <= self.n:
            self.state[i] = tuple(int(max(0, min(255, c))) for c in rgb)

    def __getitem__(self, i):
        return self.state[i]

    def __len__(self):
        return self.n

    def write(self):
        pass

    def fill(self, rgb):
        for i in range(1, self.n + 1):
            self[i] = rgb


class _Tildagonos:
    def __init__(self, n=NUM_LEDS):
        self.leds = _Leds(n)

    def set_led_power(self, on):
        pass


class _IMU:
    """Scripted IMU. The runner advances .t; acc_read()/gyro_read() return a
    slowly-orbiting tilt so motion-reactive demos visibly respond in the sim.
    On the real badge the app's try/except picks up the genuine sensor."""
    def __init__(self):
        self.t = 0.0

    def _tilt(self):
        return (0.85 * math.sin(self.t * 0.9), 0.85 * math.cos(self.t * 0.9))

    def acc_read(self):
        ax, ay = self._tilt()
        return [ax, ay, 1.0]

    def gyro_read(self):
        ax, ay = self._tilt()
        return [ay * 40.0, -ax * 40.0, 0.0]


def install_fakes(num_leds=NUM_LEDS):
    """Register the fake badge modules in sys.modules and return a handle with
    the live eventbus / buttons / tildagonos / imu for the runner to drive."""
    handle = types.SimpleNamespace()

    appmod = types.ModuleType("app")
    appmod.App = FakeApp
    sys.modules["app"] = appmod

    events = types.ModuleType("events")
    ev_in = types.ModuleType("events.input")
    ev_in.Buttons = Buttons
    ev_in.BUTTON_TYPES = BUTTON_TYPES
    events.input = ev_in
    sys.modules["events"] = events
    sys.modules["events.input"] = ev_in

    bus = _EventBus()
    system = types.ModuleType("system")
    eb = types.ModuleType("system.eventbus")
    eb.eventbus = bus
    sched = types.ModuleType("system.scheduler")
    sched_ev = types.ModuleType("system.scheduler.events")
    sched_ev.RequestForegroundPushEvent = RequestForegroundPushEvent
    sched_ev.RequestForegroundPopEvent = RequestForegroundPopEvent
    pd = types.ModuleType("system.patterndisplay")
    pd_ev = types.ModuleType("system.patterndisplay.events")
    pd_ev.PatternDisable = PatternDisable
    pd_ev.PatternEnable = PatternEnable
    pd_ev.PatternReload = PatternReload
    pd_ev.PatternSet = PatternSet
    for name, mod in (("system", system), ("system.eventbus", eb),
                      ("system.scheduler", sched),
                      ("system.scheduler.events", sched_ev),
                      ("system.patterndisplay", pd),
                      ("system.patterndisplay.events", pd_ev)):
        sys.modules[name] = mod

    # app.App is also importable as `from app import App`
    # HexpansionConfig lives in app_components on device
    appcomp = types.ModuleType("app_components")
    tokens = types.ModuleType("app_components.tokens")
    tokens.display_x = SIZE
    tokens.display_y = SIZE
    tokens.display_height_inches = 1.28
    appcomp.tokens = tokens
    sys.modules["app_components"] = appcomp
    sys.modules["app_components.tokens"] = tokens

    tg = _Tildagonos(num_leds)
    tgmod = types.ModuleType("tildagonos")
    tgmod.tildagonos = tg
    sys.modules["tildagonos"] = tgmod

    imu = _IMU()
    imumod = types.ModuleType("imu")
    imumod.acc_read = imu.acc_read
    imumod.gyro_read = imu.gyro_read
    imumod.IMU = lambda *a, **k: imu
    sys.modules["imu"] = imumod

    handle.eventbus = bus
    handle.buttons = Buttons
    handle.tildagonos = tg
    handle.imu = imu
    return handle


def load_app(path, port=None):
    """exec() a demo's app.py in a fresh namespace and instantiate its
    __app_export__ (loading by path so keyword directory names like `for` are
    fine). Tries App(config=...) then App(), mirroring the badge launcher."""
    with open(path) as f:
        src = f.read()
    ns = {"__name__": "__badge_app__", "__file__": path}
    exec(compile(src, path, "exec"), ns)
    cls = ns["__app_export__"]
    cfg = HexpansionConfig(port) if port else None
    try:
        return cls(config=cfg)
    except TypeError:
        return cls()


# --------------------------------------------------------------------------- #
#  Frame output: PPM (P6), optionally composited with the LED ring.           #
# --------------------------------------------------------------------------- #
def _round_mask(fb, size, dim=0.10):
    """Dim pixels outside the inscribed circle so previews look like the real
    round screen (the framebuffer itself is square)."""
    c = size / 2.0
    r2 = (c - 0.5) ** 2
    for y in range(size):
        for x in range(size):
            if (x + 0.5 - c) ** 2 + (y + 0.5 - c) ** 2 > r2:
                o = (y * size + x) * 3
                fb[o] = int(fb[o] * dim)
                fb[o + 1] = int(fb[o + 1] * dim)
                fb[o + 2] = int(fb[o + 2] * dim)


def compose(ctx, leds=None, round_mask=True):
    """Return (width, height, RGB bytes). If any LED is lit, draw the ring of
    LED dots in a margin around the round display."""
    fb = bytearray(ctx.fb)
    if round_mask:
        _round_mask(fb, ctx.size)
    if leds is None or all(c == (0, 0, 0) for c in leds.state[1:]):
        return ctx.size, ctx.size, fb
    margin = 34
    W = ctx.size + margin * 2
    out = bytearray(W * W * 3)     # black canvas
    off = margin
    for y in range(ctx.size):      # paste display
        src = y * ctx.size * 3
        dst = ((y + off) * W + off) * 3
        out[dst:dst + ctx.size * 3] = fb[src:src + ctx.size * 3]
    cx = cy = W / 2.0
    ring_r = ctx.size / 2.0 + margin * 0.55
    for i in range(1, leds.n + 1):
        ang = -math.pi / 2 + (i - 1) * (2 * math.pi / leds.n)
        lx = cx + ring_r * math.cos(ang)
        ly = cy + ring_r * math.sin(ang)
        r, g, b = leds.state[i]
        _disc_into(out, W, lx, ly, 9, (r, g, b))
    return W, W, out


def _disc_into(buf, W, cx, cy, rad, rgb):
    r, g, b = rgb
    r2 = rad * rad
    for y in range(int(cy - rad), int(cy + rad) + 1):
        for x in range(int(cx - rad), int(cx + rad) + 1):
            if 0 <= x < W and 0 <= y < W and (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                o = (y * W + x) * 3
                buf[o] = r
                buf[o + 1] = g
                buf[o + 2] = b


def save_ppm(path, w, h, rgb):
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(bytes(rgb))
