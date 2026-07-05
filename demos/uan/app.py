# uan (1) -- Tixy grid. One tiny formula drives a 16x16 field of dots; the sign
# picks warm/cool, the magnitude picks size. LEFT/RIGHT cycle formulas,
# UP/DOWN change speed, CANCEL exits. After tixy.land.
#
#   sim:   python3 demos/sim/run.py uan --gif
#   badge: drop demos/uan into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

N = 16
STEP = 13                       # px between cell centres
ORIG = -(N - 1) * STEP / 2.0    # centres the 16x16 grid on the screen
RMAX = STEP * 0.46


def _f_waves(t, i, x, y):
    return math.sin(t + x * 0.6) + math.cos(t * 0.9 + y * 0.6)


def _f_spin(t, i, x, y):
    return math.sin(t * 2 + i * 0.15)


def _f_ripple(t, i, x, y):
    d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
    return math.sin(d * 0.9 - t * 2.2)


def _f_plaid(t, i, x, y):
    return math.sin(x * 0.7 - t) * math.cos(y * 0.7 - t * 1.3)


def _f_bloom(t, i, x, y):
    d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
    return 3.2 - d + math.sin(t) * 2.4


FORMULAS = (_f_waves, _f_spin, _f_ripple, _f_plaid, _f_bloom)
NAMES = ("waves", "spin", "ripple", "plaid", "bloom")


class Uan(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.mode = 0
        self.speed = 1.0
        # precompute the cell centres once
        self.cells = [(ORIG + x * STEP, ORIG + y * STEP, x, y)
                      for y in range(N) for x in range(N)]

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += (delta / 1000.0) * self.speed
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.mode = (self.mode + 1) % len(FORMULAS)
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.mode = (self.mode - 1) % len(FORMULAS)
        if b.get(BUTTON_TYPES["UP"]):
            b.clear()
            self.speed = min(4.0, self.speed * 1.5)
        if b.get(BUTTON_TYPES["DOWN"]):
            b.clear()
            self.speed = max(0.15, self.speed / 1.5)
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        fn = FORMULAS[self.mode]
        t = self.t
        for (px, py, x, y) in self.cells:
            v = fn(t, y * N + x, x, y)
            a = v if v >= 0 else -v
            if a < 0.08:
                continue
            if a > 1.0:
                a = 1.0
            r = 1.5 + a * (RMAX - 1.5)
            al = 0.35 + 0.65 * a
            if v > 0:
                ctx.rgba(1.0, 0.55, 0.15, al)
            else:
                ctx.rgba(0.2, 0.55, 1.0, al)
            ctx.arc(px, py, r, 0, 6.2832, True).fill()
        ctx.rgb(0.7, 0.7, 0.7)
        ctx.font_size = 16
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 112).text(NAMES[self.mode])
        ctx.restore()


__app_export__ = Uan
