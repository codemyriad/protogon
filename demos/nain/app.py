# nain (9) -- Plasma tiles. A coarse 16x16 grid of rectangle fills, each coloured
# by a sum of sines -- the classic plasma effect without a per-pixel framebuffer.
# RIGHT cycles the palette, CANCEL exits.
#
#   sim: python3 demos/sim/run.py nain --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

N = 16
STEP = 240 / N                  # 15 px tiles, edge to edge


class Nain(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.pal = 0

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
            self.pal = (self.pal + 1) % 3
        return True

    def _col(self, v):
        # v in 0..1
        if self.pal == 0:                            # fire
            return (min(1.0, v * 1.6),
                    max(0.0, v * 1.4 - 0.4),
                    max(0.0, v * 0.6 - 0.4))
        if self.pal == 1:                            # ocean
            return (v * 0.2, 0.3 + v * 0.6, 0.5 + v * 0.5)
        # rainbow
        a = v * 6.28318
        return (0.5 + 0.5 * math.sin(a),
                0.5 + 0.5 * math.sin(a + 2.09),
                0.5 + 0.5 * math.sin(a + 4.19))

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        for gy in range(N):
            y = -120 + gy * STEP
            fy = gy - 7.5
            for gx in range(N):
                fx = gx - 7.5
                v = (math.sin(fx * 0.6 + t)
                     + math.sin(fy * 0.7 - t * 1.1)
                     + math.sin((fx + fy) * 0.45 + t * 0.7)
                     + math.sin(((fx * fx + fy * fy) ** 0.5) * 0.7 - t * 1.7))
                v = (v + 4.0) / 8.0
                r, g, bl = self._col(v)
                ctx.rgb(max(0.0, min(1.0, r)),
                        max(0.0, min(1.0, g)),
                        max(0.0, min(1.0, bl)))
                ctx.rectangle(-120 + gx * STEP, y, STEP + 0.6, STEP + 0.6).fill()
        ctx.restore()


__app_export__ = Nain
