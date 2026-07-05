# seven (7) -- Hopalong plotter. Barry Martin's attractor:
#   x' = y - sign(x)*sqrt(|b*x - c|);  y' = a - x
# A few thousand iterated points make a strange-attractor cloud; the badge is a
# maths screensaver. RIGHT cycles (a,b,c) presets, CANCEL exits.
#
#   sim: python3 demos/sim/run.py seven --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

PRESETS = ((-2.0, 0.35, 1.2, 3.6),
           (2.1, 1.9, 0.5, 2.2),
           (-3.1, 0.2, 1.9, 2.6),
           (1.3, 1.3, 1.3, 3.0))     # (a, b, c, scale)
# Each retained point is one path+fill on the badge, and a full redraw runs at
# ~8-14 fps, so keep the cloud well under the ~500-primitive/frame budget. (The
# host sim rasterises thousands of rects instantly and would hide the stall.)
KEEP = 440
PER = 14                             # new points per frame


def _hue(h):
    h = h - int(h)
    i = int(h * 6)
    f = h * 6 - i
    q = 1.0 - f
    if i == 0:
        return (1.0, f, 0.0)
    if i == 1:
        return (q, 1.0, 0.0)
    if i == 2:
        return (0.0, 1.0, f)
    if i == 3:
        return (0.0, q, 1.0)
    if i == 4:
        return (f, 0.0, 1.0)
    return (1.0, 0.0, q)


class Seven(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.preset = 0
        self._reset()

    def _reset(self):
        self.x = 0.0
        self.y = 0.0
        self.pts = []

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.preset = (self.preset + 1) % len(PRESETS)
            self._reset()
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.preset = (self.preset - 1) % len(PRESETS)
            self._reset()
        a, bb, c, _ = PRESETS[self.preset]
        x, y = self.x, self.y
        for _ in range(PER):
            xn = y - (1.0 if x > 0 else (-1.0 if x < 0 else 0.0)) * \
                math.sqrt(abs(bb * x - c))
            y = a - x
            x = xn
            self.pts.append((x, y))
        self.x, self.y = x, y
        if len(self.pts) > KEEP:
            self.pts = self.pts[-KEEP:]
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        sc = PRESETS[self.preset][3] * 7.0
        ctx.rotate(self.t * 0.15)
        n = len(self.pts)
        base = self.t * 0.1
        for idx in range(n):
            px, py = self.pts[idx]
            x = px * sc
            y = py * sc
            if x < -118 or x > 118 or y < -118 or y > 118:
                continue
            r, g, bl = _hue(base + idx * 0.0006)
            al = 0.25 + 0.75 * (idx / n)
            ctx.rgba(r, g, bl, al)
            ctx.rectangle(x, y, 1.6, 1.6).fill()
        ctx.restore()


__app_export__ = Seven
