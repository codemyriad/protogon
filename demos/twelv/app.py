# twelv (12) -- Cellular playground. A wrap-around grid where every cell obeys
# one tiny neighbour rule: Life, Brian's Brain, or cyclic.
#
# HOW IT WORKS
#   The grid is a tiny world: a few times a second every cell looks at its
#   eight neighbours and one rule picks its fate. LIFE: born next to exactly
#   3 live cells, survive with 2-3 (survivors slowly blush red). BRAIN: fire,
#   tire, rest -- rest ignites beside exactly 2 sparks. CYCLIC: four colours,
#   each eating the one before it. Nobody plans it; patterns grow themselves.
#
# BUTTONS   RIGHT/LEFT next rule - CONFIRM fresh random seed - CANCEL exits
#
#   sim:   python3 demos/sim/run.py twelv --gif
#   badge: drop demos/twelv into the official simulator's sim/apps/ (see README)
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
GRID       = 20                # cells per side .... try 14; >20 chugs the badge
CELL       = 10                # px per cell ....... try 11 to fill the screen
STEP_EVERY = 3                 # frames per generation ..... 1 races, 8 crawls
SEED       = 0.32              # fraction alive on reseed  lonely 0.1, mobbed 0.6
GAP        = 0.6               # grout between cells  0.0 fuses, 3.0 makes beads
AGE_TINT   = 0.1               # how fast Life survivors blush red .... try 0.5
FIRING     = (0.4, 0.8, 1.0)   # Brian's Brain spark colour (electric blue)

OFF = -(GRID - 1) * CELL / 2.0     # leftmost column, so the grid sits centred

# ------------------------------ the rules ------------------------------------
# A rule answers one question for one cell: "given my state s and my eight
# neighbours, what am I next?" step() below asks every cell, each generation.

def life(s, nbrs):
    # Conway's Game of Life: born next to exactly 3, survive on 2 or 3
    n = sum(nbrs)
    return 1 if n == 3 or (s and n == 2) else 0

def brain(s, nbrs):
    # Brian's Brain: firing (1) tires (2), tired rests (0), and a resting
    # cell ignites beside exactly 2 sparks -- endless travelling waves
    if s:
        return (s + 1) % 3
    return 1 if sum(1 for v in nbrs if v == 1) == 2 else 0

def cyclic(s, nbrs):
    # four colours chase in a circle: s is eaten by colour s+1 the moment
    # one touches it up, down, left or right (those are nbrs 1, 3, 4, 6)
    eater = (s + 1) % 4
    return eater if eater in (nbrs[1], nbrs[3], nbrs[4], nbrs[6]) else s

RULES = (life, brain, cyclic)
NAMES = ("life", "brain", "cyclic")
CYCLE_COLOURS = ((1.0, 0.3, 0.2), (0.9, 0.8, 0.2),    # cyclic's four tribes:
                 (0.2, 0.8, 0.5), (0.3, 0.4, 1.0))    # red yellow green blue


class Twelv(app.App):
    """Count frames, step the world every few, paint every living cell."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False    # have we taken the screen yet?
        self.rule = 0      # which rule is live
        self.frame = 0     # frames seen -- a generation every STEP_EVERY
        self.reseed()

    def reseed(self):
        # scatter a fresh random soup; every cell starts at age zero
        self.cur = [[1 if random.random() < SEED else 0
                     for _ in range(GRID)] for _ in range(GRID)]
        self.age = [[0] * GRID for _ in range(GRID)]

    def step(self, rule):
        # % GRID wraps the edges: a glider leaving the right re-enters left
        g = self.cur
        nxt = [[0] * GRID for _ in range(GRID)]
        for y in range(GRID):
            ym, yp = (y - 1) % GRID, (y + 1) % GRID
            for x in range(GRID):
                xm, xp = (x - 1) % GRID, (x + 1) % GRID
                v = rule(g[y][x], (g[ym][xm], g[ym][x], g[ym][xp], g[y][xm],
                                   g[y][xp], g[yp][xm], g[yp][x], g[yp][xp]))
                nxt[y][x] = v
                self.age[y][x] = self.age[y][x] + 1 if v else 0
        self.cur = nxt

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
            self.reseed()
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.rule = (self.rule + 1) % len(RULES)
            self.reseed()
        self.frame += 1
        if self.frame % max(1, STEP_EVERY) == 0:   # max() survives a drag to 0
            self.step(RULES[self.rule % len(RULES)])
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        rule = self.rule % len(RULES)
        for y in range(GRID):
            top = OFF + y * CELL - CELL / 2
            for x in range(GRID):
                v = self.cur[y][x]
                if v == 0:
                    continue          # empty cells stay black and cost nothing
                if rule == 0:
                    blush = min(1.0, self.age[y][x] * AGE_TINT)
                    ctx.rgb(0.2 + 0.8 * blush, 1.0 - 0.6 * blush, 0.3)
                elif rule == 1:
                    c = FIRING if v == 1 else (0.1, 0.2, 0.4)   # tired = dim
                    ctx.rgb(c[0], c[1], c[2])
                else:
                    c = CYCLE_COLOURS[v % 4]
                    ctx.rgb(c[0], c[1], c[2])
                ctx.rectangle(OFF + x * CELL - CELL / 2, top,
                              CELL - GAP, CELL - GAP).fill()
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.font_size = 14
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 112).text(NAMES[rule])
        ctx.restore()


__app_export__ = Twelv

# ------------------------------ try this --------------------------------------
# - in reseed(), swap `1 if random.random() < SEED else 0` for
#   `random.randrange(4)`, then press RIGHT until "cyclic": spiral storms
# - in life(), change `n == 3` to `n in (3, 6)` -- a close cousin of
#   HighLife: the soup suddenly grows lacy, self-copying structures
# - in brain(), change `== 2` to `== 1`: every lone spark blooms into a ring
