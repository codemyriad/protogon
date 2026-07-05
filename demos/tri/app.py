# tri (3) -- Qix tracer. A few points bounce in a box; the polyline joining them
# leaves a fading trail. The 12 LED ring mirrors the head colour. CONFIRM adds a
# point (2->3->4->2), RIGHT changes the palette, CANCEL exits.
#
#   sim: python3 demos/sim/run.py tri --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

BOX = 106
TRAIL = 42


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


class Tri(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.npts = 3
        self.palette = 0
        self.trail = []          # list of frames; each = list of (x,y)
        self._spawn()

    def _spawn(self):
        import random
        self.pts = []
        for _ in range(self.npts):
            ang = random.uniform(0, 6.28)
            sp = random.uniform(70, 110)
            self.pts.append([random.uniform(-BOX, BOX),
                             random.uniform(-BOX, BOX),
                             math.cos(ang) * sp, math.sin(ang) * sp])
        self.trail = []

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())      # take the LED ring
            self.fg = True
        dt = delta / 1000.0
        self.t += dt
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())       # hand the ring back
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self.npts = 2 + (self.npts - 1) % 3
            self._spawn()
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.palette = (self.palette + 1) % 3
        for p in self.pts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[0] < -BOX or p[0] > BOX:
                p[2] = -p[2]
                p[0] = max(-BOX, min(BOX, p[0]))
            if p[1] < -BOX or p[1] > BOX:
                p[3] = -p[3]
                p[1] = max(-BOX, min(BOX, p[1]))
        self.trail.append([(p[0], p[1]) for p in self.pts])
        if len(self.trail) > TRAIL:
            self.trail.pop(0)
        self._leds()
        return True

    def _headcol(self):
        if self.palette == 0:
            return _hue((self.t * 0.15) % 1.0)
        if self.palette == 1:
            return (1.0, 0.4, 0.1)
        return (0.3, 0.9, 1.0)

    def _leds(self):
        r, g, bl = self._headcol()
        base = self.t * 2.0
        for i in range(1, 13):
            f = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(base + i * 0.52))
            tildagonos.leds[i] = (int(r * 255 * f), int(g * 255 * f),
                                  int(bl * 255 * f))
        tildagonos.leds.write()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        n = len(self.trail)
        hr, hg, hb = self._headcol()
        for idx in range(n):
            frame = self.trail[idx]
            age = (idx + 1) / n
            al = age * age
            ctx.line_width = 1.0 + 2.0 * age
            ctx.rgba(hr, hg, hb, al * 0.9)
            first = frame[0]
            ctx.move_to(first[0], first[1])
            for (x, y) in frame[1:]:
                ctx.line_to(x, y)
            ctx.line_to(first[0], first[1])
            ctx.stroke()
        # bright heads
        ctx.rgb(1, 1, 1)
        for (x, y) in self.trail[-1] if self.trail else []:
            ctx.arc(x, y, 3, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Tri
