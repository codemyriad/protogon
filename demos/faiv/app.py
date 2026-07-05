# faiv (5) -- Polar tunnel. A stack of concentric rings whose brightness follows
# sin(k*r - w*t); a wandering centre makes the whole screen breathe. Not a
# per-pixel tunnel -- a vector approximation that still reads as depth.
# RIGHT cycles the colour scheme, CANCEL exits.
#
#   sim: python3 demos/sim/run.py faiv --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

NR = 22
TAU = 6.28318


class Faiv(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.scheme = 0
        self.radii = [6 + k * 5.2 for k in range(NR)]

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
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.scheme = (self.scheme + 1) % 3
        return True

    def _col(self, v):
        # v in 0..1 brightness
        if self.scheme == 0:
            return (v, v, min(1.0, v * 1.1))            # cool white
        if self.scheme == 1:
            return (min(1.0, v * 1.4), v * 0.6, v * 0.15)   # fire
        return (v * 0.2, v * 0.8, min(1.0, v * 1.3))    # ice

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        ox = math.sin(t * 0.7) * 12.0
        oy = math.cos(t * 0.9) * 12.0
        for k in range(NR):
            r = self.radii[k]
            v = 0.5 + 0.5 * math.sin(k * 0.55 - t * 3.0)
            v = v * v
            cr, cg, cb = self._col(v)
            ctx.line_width = 2.0 + v * 4.0
            # centre wobble scaled so far rings move less (parallax)
            f = k / NR
            ctx.rgba(cr, cg, cb, 0.5 + 0.5 * v)
            ctx.arc(ox * (1 - f), oy * (1 - f), r, 0, TAU, True).stroke()
        ctx.restore()


__app_export__ = Faiv
