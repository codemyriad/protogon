# thurteen (13) -- Drift lines. A handful of anchor points drift on slow sine
# orbits; a smooth quadratic spline threads them into a ribbon, and a few phase-
# shifted copies braid together. RIGHT changes the ribbon count, CANCEL exits.
#
#   sim: python3 demos/sim/run.py thurteen --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

M = 7                           # anchors per ribbon
COLS = ((0.3, 0.8, 1.0), (1.0, 0.4, 0.7), (0.6, 1.0, 0.5),
        (1.0, 0.8, 0.3), (0.7, 0.5, 1.0))


class Thurteen(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.count = 3

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
            self.count = 2 + self.count % 5
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.count = 2 + (self.count - 2 + 3) % 5
        return True

    def _anchors(self, phase):
        pts = []
        for i in range(M):
            x = -108 + i * (216 / (M - 1))
            y = math.sin(self.t * 0.8 + i * 0.9 + phase) * 70 \
                + math.sin(self.t * 0.35 + i) * 20
            x += math.cos(self.t * 0.5 + i * 1.3 + phase) * 12
            pts.append((x, y))
        return pts

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        for r in range(self.count):
            phase = r * (6.28318 / self.count)
            pts = self._anchors(phase)
            cr, cg, cb = COLS[r % len(COLS)]
            ctx.line_width = 2.5
            ctx.rgba(cr, cg, cb, 0.85)
            ctx.move_to(pts[0][0], pts[0][1])
            for i in range(1, M - 1):
                mx = (pts[i][0] + pts[i + 1][0]) / 2.0
                my = (pts[i][1] + pts[i + 1][1]) / 2.0
                ctx.quad_to(pts[i][0], pts[i][1], mx, my)
            ctx.line_to(pts[M - 1][0], pts[M - 1][1])
            ctx.stroke()
        ctx.restore()


__app_export__ = Thurteen
