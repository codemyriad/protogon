# sics (6) -- Hex kaleidoscope. Draw one small motif in a wedge, then stamp it
# N-fold around the centre with ctx.rotate (plus a mirror). CONFIRM randomises
# the motif, RIGHT/LEFT change the symmetry (6/8/12), CANCEL exits.
#
#   sim: python3 demos/sim/run.py sics --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

TAU = 6.28318
SYMS = (6, 8, 12)


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


class Sics(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.symi = 0
        self._reseed()

    def _reseed(self):
        import random
        self.orbit = random.uniform(30, 80)
        self.spin = random.uniform(0.6, 2.2) * random.choice((-1, 1))
        self.dot = random.uniform(6, 16)
        self.hue = random.random()
        self.reach = random.uniform(60, 105)

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
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self._reseed()
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.symi = (self.symi + 1) % len(SYMS)
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.symi = (self.symi - 1) % len(SYMS)
        return True

    def _motif(self, ctx):
        t = self.t
        a = t * self.spin
        ox = math.cos(a) * self.orbit
        oy = math.sin(a) * self.orbit * 0.5
        r, g, bl = _hue(self.hue + t * 0.05)
        ctx.line_width = 2.0
        ctx.rgba(r, g, bl, 0.9)
        ctx.move_to(0, 0).line_to(self.reach, 0).stroke()
        ctx.rgba(bl, r, g, 0.85)
        ctx.arc(ox, oy, self.dot, 0, TAU, True).fill()
        ctx.rgba(g, bl, r, 0.6)
        ctx.arc(self.reach * 0.7, 6, self.dot * 0.5, 0, TAU, True).fill()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        sym = SYMS[self.symi]
        ctx.translate(0, 0)
        ctx.rotate(self.t * 0.2)
        for s in range(sym):
            ctx.save()
            ctx.rotate(TAU * s / sym)
            self._motif(ctx)
            ctx.scale(1.0, -1.0)      # mirror the wedge
            self._motif(ctx)
            ctx.restore()
        ctx.restore()


__app_export__ = Sics
