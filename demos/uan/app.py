# uan (1) -- Tixy grid. One tiny formula drives a 16x16 field of dots; the sign
# picks warm/cool, the magnitude picks size. After tixy.land.
#
# HOW IT WORKS
#   Every frame, each dot asks one little formula: "how big should I be?"
#   The formula gets the time t, the dot's column x and row y, and answers
#   with a number around -1..1:
#       positive -> warm colour      negative -> cool colour
#       close to 0 -> tiny dot       close to 1 -> big dot
#   That's the whole machine. Five formulas are included -- write your own.
#
# BUTTONS   LEFT/RIGHT swap formula - UP/DOWN change speed - CANCEL exits
#
#   sim:   python3 demos/sim/run.py uan --gif
#   badge: drop demos/uan into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
GRID    = 16                  # dots per side .. try 8 (chunky); 24 chugs the badge
SPACING = 13.0                # px between dot centres.. spread them out: 15.0
DOT_MIN = 1.5                 # radius of the smallest visible dot
WARM    = (1.0, 0.55, 0.15)   # colour for positive values (amber)
COOL    = (0.2, 0.55, 1.0)    # colour for negative values (sky blue)

# ----------------------------- the formulas ----------------------------------
# A formula gets (t, i, x, y): t = seconds, x/y = column/row (0..GRID-1),
# i = the dot's number. Return roughly -1..1. Edit one. Break one. Add one.

def waves(t, i, x, y):
    # two ripples sliding across each other, one per axis
    return math.sin(t + x * 0.6) + math.cos(t * 0.9 + y * 0.6)

def spin(t, i, x, y):
    # every dot pulses, offset by its number -> a rolling shimmer
    return math.sin(t * 2 + i * 0.15)

def ripple(t, i, x, y):
    # rings spreading from a point, like a stone dropped in water
    # (7.5 is the centre of a 16-wide grid -- drag it to move the splash)
    d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
    return math.sin(d * 0.9 - t * 2.2)

def plaid(t, i, x, y):
    # horizontal waves times vertical waves = woven cloth
    return math.sin(x * 0.7 - t) * math.cos(y * 0.7 - t * 1.3)

def bloom(t, i, x, y):
    # a disc that grows and shrinks with a slow heartbeat
    d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
    return 3.2 - d + math.sin(t) * 2.4

FORMULAS = (waves, spin, ripple, plaid, bloom)
NAMES = ("waves", "spin", "ripple", "plaid", "bloom")


class Uan(app.App):
    """Keep time, listen to buttons, ask the formula, draw the dots."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # seconds since start, scaled by speed
        self.mode = 0          # which formula is live
        self.speed = 1.0
        # precompute each dot's screen position once
        origin = -(GRID - 1) * SPACING / 2.0   # centres the grid
        self.cells = [(origin + x * SPACING, origin + y * SPACING, x, y)
                      for y in range(GRID) for x in range(GRID)]

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
        formula = FORMULAS[self.mode % len(FORMULAS)]
        dot_max = SPACING * 0.46          # biggest dot that still leaves a gap
        for (px, py, x, y) in self.cells:
            value = formula(self.t, y * GRID + x, x, y)
            size = abs(value)
            if size < 0.08:               # too small to see -- skip it
                continue
            if size > 1.0:
                size = 1.0
            colour = WARM if value > 0 else COOL
            ctx.rgba(colour[0], colour[1], colour[2], 0.35 + 0.65 * size)
            ctx.arc(px, py, DOT_MIN + size * (dot_max - DOT_MIN),
                    0, 6.2832, True).fill()
        ctx.rgb(0.7, 0.7, 0.7)
        ctx.font_size = 16
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 112).text(NAMES[self.mode % len(NAMES)])
        ctx.restore()


__app_export__ = Uan

# ------------------------------ try this --------------------------------------
# - drag the 7.5 in ripple() sideways and watch the splash centre follow you
# - in waves(), change math.cos to math.sin -- then try math.tan (chaos)
# - add your own formula:  def stripes(t, i, x, y): return math.sin(x - t * 3)
#   then add it to FORMULAS and NAMES, and press RIGHT until it comes up
