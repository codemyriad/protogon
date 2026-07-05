# eit (8) -- Matrix rain, round-cropped. Glyph columns fall; the head is bright,
# the tail fades, and anything off the round screen is skipped. RIGHT cycles the
# colour (green/amber/cyan/violet), CANCEL exits.
#
#   sim: python3 demos/sim/run.py eit --gif
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

GLYPHS = "0123456789ABCDFHKMNPXYZ#*<>/"
CELL = 15                       # px per glyph row
COLS = 15
R2 = 116 * 116
TINTS = ((0.3, 1.0, 0.4), (1.0, 0.7, 0.1), (0.3, 0.9, 1.0), (0.8, 0.4, 1.0))


class Eit(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.tint = 0
        self.cols = []
        span = (COLS - 1) * CELL
        for c in range(COLS):
            x = -span / 2.0 + c * CELL
            self.cols.append(self._newcol(x, start=random.uniform(-140, 40)))

    def _newcol(self, x, start=-140):
        return {"x": x,
                "y": start,
                "sp": random.uniform(45, 130),
                "len": random.randint(6, 16),
                "g": [random.choice(GLYPHS) for _ in range(20)]}

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        dt = delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.tint = (self.tint + 1) % len(TINTS)
        for col in self.cols:
            col["y"] += col["sp"] * dt
            if random.random() < 0.15:            # mutate a glyph
                col["g"][random.randint(0, 19)] = random.choice(GLYPHS)
            if col["y"] - col["len"] * CELL > 128:
                col.update(self._newcol(col["x"]))
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = 15
        ctx.text_align = ctx.LEFT
        tr, tg, tb = TINTS[self.tint]
        for col in self.cols:
            x = col["x"]
            head = col["y"]
            for k in range(col["len"]):
                gy = head - k * CELL
                if gy < -120 or gy > 120:
                    continue
                if x * x + gy * gy > R2:
                    continue
                if k == 0:
                    ctx.rgb(0.9, 1.0, 0.9)             # bright head
                else:
                    f = 1.0 - k / col["len"]
                    ctx.rgba(tr * f, tg * f, tb * f, 0.25 + 0.75 * f)
                ctx.move_to(x, gy).text(col["g"][k % 20])
        ctx.restore()


__app_export__ = Eit
