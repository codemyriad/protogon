# ciu (2) -- Moire rings. Two families of thin rings drift past each other with
# a slight phase mismatch; the interference does the work, not the code.
# RIGHT toggles circles <-> hexagons, CANCEL exits.
#
#   sim: python3 demos/sim/run.py ciu --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

NR = 11                 # rings per family
TAU = 6.28318


class Ciu(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.hexed = False

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += delta / 1500.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.hexed = not self.hexed
        return True

    def _ring(self, ctx, cx, cy, r, rot):
        if not self.hexed:
            ctx.arc(cx, cy, r, 0, TAU, True).stroke()
            return
        ctx.begin_path()
        for k in range(7):
            a = rot + k * (TAU / 6)
            x = cx + r * math.cos(a)
            y = cy + r * math.sin(a)
            if k == 0:
                ctx.move_to(x, y)
            else:
                ctx.line_to(x, y)
        ctx.stroke()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 1.6
        t = self.t
        for k in range(NR):
            a = t + k * 0.30
            ox = math.sin(a) * 30.0
            oy = math.cos(a * 1.3) * 30.0
            r = 14 + k * 8
            ctx.rgba(0.15 + 0.05 * k, 0.75, 1.0, 0.42)
            self._ring(ctx, ox, oy, r, t * 0.4)
            ctx.rgba(1.0, 0.25 + 0.04 * k, 0.55, 0.40)
            self._ring(ctx, -ox, -oy, r, -t * 0.4)
        ctx.restore()


__app_export__ = Ciu
