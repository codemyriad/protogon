# matrixrain (8) -- Matrix rain, round-cropped. Glyph columns fall with bright heads
# and fading tails; RIGHT cycles the colour.
#
# HOW IT WORKS
#   Each column is one raindrop made of letters: a bright head that falls at
#   its own speed, towing a tail of glyphs that fade the further back they
#   sit. Every frame each column answers three questions: how far did I fall?
#   (speed x time) -- do I flicker a letter? (a dice roll) -- am I off the
#   bottom? (then restart above the top with a fresh speed and tail length).
#   Letters that would land outside the round glass are simply not drawn.
#
# PRIOR ART  the Matrix digital rain (The Matrix, 1999) --
#            https://en.wikipedia.org/wiki/Matrix_digital_rain
#
# BUTTONS   RIGHT/LEFT cycle the colour - CANCEL exits
#
#   sim:   python3 demos/sim/run.py matrixrain --gif
#   badge: drop demos/matrixrain into the official simulator's sim/apps/ (see README)
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
COLS     = 15     # columns of rain ........ try 8 (sparse) or 22 (dense)
CELL     = 15     # glyph size AND row spacing, px .. chunky rain: 24
FALL_MIN = 45.0   # slowest column, px per second
FALL_MAX = 130.0  # fastest column ......... storm: 300.0
TAIL_MIN = 6      # shortest tail, in glyphs
TAIL_MAX = 16     # longest tail ........... long streamers: 24
FLICKER  = 0.15   # chance per frame a column swaps a letter .. boiling: 0.9
TINTS = ((0.3, 1.0, 0.4),   # phosphor green   <- RIGHT cycles these four
         (1.0, 0.7, 0.1),   # amber terminal
         (0.3, 0.9, 1.0),   # ice cyan
         (0.8, 0.4, 1.0))   # violet

GLYPHS = "0123456789ABCDFHKMNPXYZ#*<>/"   # the alphabet the rain is made of
R2 = 116 * 116            # the glass is round: skip glyphs past radius 116


def new_column(x, head_y):
    # one raindrop: where it is, how fast it falls, and the letters it tows
    return {"x": x,
            "y": head_y,
            "speed": random.uniform(FALL_MIN, FALL_MAX),
            "tail": random.randint(TAIL_MIN, TAIL_MAX),
            "glyphs": [random.choice(GLYPHS) for _ in range(20)]}


class Matrixrain(app.App):
    """Move every column down a little, flicker a letter, redraw the rain."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False     # have we taken the screen yet?
        self.tint = 0       # which colour is live
        # one column per slot across the screen, each starting mid-fall
        span = (COLS - 1) * CELL
        self.cols = [new_column(-span / 2.0 + c * CELL,
                                random.uniform(-140, 40))
                     for c in range(COLS)]

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
            col["y"] += col["speed"] * dt
            if random.random() < FLICKER:            # swap one letter, anywhere
                col["glyphs"][random.randint(0, 19)] = random.choice(GLYPHS)
            if col["y"] - col["tail"] * CELL > 128:  # whole tail is off-screen
                col.update(new_column(col["x"], -140))
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.font_size = CELL
        ctx.text_align = ctx.LEFT
        tint = TINTS[self.tint % len(TINTS)]
        for col in self.cols:
            x = col["x"]
            head = col["y"]
            for k in range(col["tail"]):
                gy = head - k * CELL                 # k glyphs behind the head
                if gy < -120 or gy > 120:
                    continue
                if x * x + gy * gy > R2:             # off the round glass
                    continue
                if k == 0:
                    ctx.rgb(0.9, 1.0, 0.9)           # the head glows near-white
                else:
                    fade = 1.0 - k / col["tail"]     # 1 at the head, 0 at the tip
                    ctx.rgba(tint[0] * fade, tint[1] * fade, tint[2] * fade,
                             0.25 + 0.75 * fade)
                ctx.move_to(x, gy).text(col["glyphs"][k % 20])
        ctx.restore()


__app_export__ = Matrixrain

# ------------------------------ try this --------------------------------------
# - set GLYPHS = "01" for binary rain, or spell something: "EMF2026 "
# - drag FLICKER to 0.9 and the letters boil; at 0.0 each column's text freezes
# - CELL = 24 with COLS = 9 makes chunky billboard rain (the font follows CELL)
