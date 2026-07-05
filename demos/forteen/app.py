# forteen (14) -- Orbiting metaballs (lite). A few blobs orbit the centre; each
# is faked as a stack of translucent discs (bright core, soft halo) so where
# they overlap the colour piles up like a metaball field -- no per-pixel maths.
# RIGHT changes the blob count, CANCEL exits.
#
#   sim: python3 demos/sim/run.py forteen --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

TAU = 6.28318
COLS = ((1.0, 0.3, 0.3), (0.3, 0.6, 1.0), (0.4, 1.0, 0.5),
        (1.0, 0.8, 0.2), (0.9, 0.4, 1.0))
HALO = 5                         # discs per blob


class Forteen(app.App):
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
            self.count = 3 + self.count % 3          # 3->4->5->3
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.count = 3 + (self.count - 1) % 3
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        for k in range(self.count):
            ph = k * (TAU / self.count)
            orbit = 40 + 18 * math.sin(t * 0.5 + k)
            x = math.cos(t * (0.6 + 0.12 * k) + ph) * orbit
            y = math.sin(t * (0.5 + 0.1 * k) + ph) * orbit * 0.9
            cr, cg, cb = COLS[k % len(COLS)]
            base = 46
            for h in range(HALO):
                f = (HALO - h) / HALO                # 1 at core
                r = base * (0.25 + 0.75 * (h + 1) / HALO)
                al = 0.10 + 0.22 * f
                ctx.rgba(cr, cg, cb, al)
                ctx.arc(x, y, r, 0, TAU, True).fill()
        ctx.restore()


__app_export__ = Forteen
