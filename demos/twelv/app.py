# twelv (12) -- Cellular playground. A 24x24 toroidal grid running one of three
# rules, live cells tinted by age. CONFIRM reseeds, RIGHT switches rule
# (Life / Brian's Brain / cyclic), CANCEL exits.
#
#   sim: python3 demos/sim/run.py twelv --gif
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# The cyclic rule saturates to ~all cells non-zero, and draw() paints one
# rectangle().fill() per live cell every frame, so keep GxG under the badge's
# ~500-primitive/frame budget (20x20 = 400 worst case). The host sim would hide
# the stall -- it fills 576 rects with no visible slowdown.
G = 20
CELL = 10
OFF = -(G - 1) * CELL / 2.0
STEP_EVERY = 3                  # frames between generations
NAMES = ("life", "brain", "cyclic")


class Twelv(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.rule = 0
        self.frame = 0
        self._seed()

    def _seed(self):
        self.cur = [[1 if random.random() < 0.32 else 0
                     for _ in range(G)] for _ in range(G)]
        self.age = [[0] * G for _ in range(G)]

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self._seed()
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.rule = (self.rule + 1) % 3
            self._seed()
        self.frame += 1
        if self.frame % STEP_EVERY == 0:
            self._generation()
        return True

    def _generation(self):
        g = self.cur
        nxt = [[0] * G for _ in range(G)]
        for y in range(G):
            ym, yp = (y - 1) % G, (y + 1) % G
            for x in range(G):
                xm, xp = (x - 1) % G, (x + 1) % G
                if self.rule == 0:                    # Conway Life
                    n = (g[ym][xm] + g[ym][x] + g[ym][xp] +
                         g[y][xm] + g[y][xp] +
                         g[yp][xm] + g[yp][x] + g[yp][xp])
                    alive = 1 if (g[y][x] and n in (2, 3)) or \
                        (not g[y][x] and n == 3) else 0
                    nxt[y][x] = alive
                    self.age[y][x] = self.age[y][x] + 1 if alive else 0
                elif self.rule == 1:                  # Brian's Brain
                    if g[y][x] == 1:
                        nxt[y][x] = 2                 # on -> dying
                    elif g[y][x] == 2:
                        nxt[y][x] = 0                 # dying -> off
                    else:
                        on = sum(1 for (dy, dx) in (
                            (ym, xm), (ym, x), (ym, xp), (y, xm), (y, xp),
                            (yp, xm), (yp, x), (yp, xp)) if g[dy][dx] == 1)
                        nxt[y][x] = 1 if on == 2 else 0
                else:                                 # cyclic (4 states)
                    s = g[y][x]
                    nextv = (s + 1) % 4
                    hit = (g[ym][x] == nextv or g[yp][x] == nextv or
                           g[y][xm] == nextv or g[y][xp] == nextv)
                    nxt[y][x] = nextv if hit else s
        self.cur = nxt

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        g = self.cur
        for y in range(G):
            py = OFF + y * CELL
            for x in range(G):
                v = g[y][x]
                if v == 0:
                    continue
                if self.rule == 0:
                    a = min(1.0, self.age[y][x] / 10.0)
                    ctx.rgb(0.2 + 0.8 * a, 1.0 - 0.6 * a, 0.3)
                elif self.rule == 1:
                    ctx.rgb(0.4, 0.8, 1.0) if v == 1 else ctx.rgb(0.1, 0.2, 0.4)
                else:
                    c = (((1.0, 0.3, 0.2), (0.9, 0.8, 0.2),
                          (0.2, 0.8, 0.5), (0.3, 0.4, 1.0))[v])
                    ctx.rgb(c[0], c[1], c[2])
                ctx.rectangle(OFF + x * CELL - CELL / 2, py - CELL / 2,
                              CELL - 0.6, CELL - 0.6).fill()
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.font_size = 14
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 112).text(NAMES[self.rule])
        ctx.restore()


__app_export__ = Twelv
