# tixy (1) -- Tixy grid. One tiny formula drives a 16x16 field of dots; the sign
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
# Credits:   tixy.land by Martin Kleppe (@aemkei) -- https://tixy.land
#
# BUTTONS   LEFT/RIGHT swap formula - UP/DOWN change speed - CANCEL exits
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-click, or tap on a phone, for a slider). The
# "MIN<n<MAX" notes set each slider's range; a/b/c pick items inside a tuple.
GRID    = 16                  # 4<n<24  dots per side.. 8 = chunky, 24 chugs
SPACING = 13.0                # 6<n<24  px between dot centres.. bigger = airier
DOT_MIN = 1.5                 # 0<n<6   radius of the smallest visible dot
WARM    = (1.0, 0.55, 0.15)   # colour for positive values (amber) -- tap the swatch
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

# --------------------------- pick the live one -------------------------------
# Click a name to run it -- the badge switches instantly, without restarting.
# (On a real badge, LEFT/RIGHT cycle through them.) It's just a commented-out
# line each: uncomment the one you want, or edit the formula above it.
LIVE = waves      #: waves
# LIVE = spin     #: spin
# LIVE = ripple   #: ripple
# LIVE = plaid    #: plaid
# LIVE = bloom    #: bloom

ORDER = (waves, spin, ripple, plaid, bloom)   # what LEFT/RIGHT cycle on a badge


class Tixy(app.App):
    # Keep time, listen to buttons, ask the formula, draw the dots.

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False            # have we taken the screen yet?
        self.t = 0.0               # seconds since start, scaled by speed
        self.formula = LIVE        # the live formula (set by the picker above)
        self.speed = 1.0
        # precompute each dot's screen position once
        origin = -(GRID - 1) * SPACING / 2.0   # centres the grid
        self.cells = [(origin + x * SPACING, origin + y * SPACING, x, y)
                      for y in range(GRID) for x in range(GRID)]

    # Carry time + speed across live edits, but NOT the formula: that way
    # clicking a new formula above swaps it in immediately.
    __live_state__ = ("t", "speed")

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
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            step = 1 if b.get(BUTTON_TYPES["RIGHT"]) else -1
            b.clear()
            here = ORDER.index(self.formula) if self.formula in ORDER else 0
            self.formula = ORDER[(here + step) % len(ORDER)]
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
        formula = self.formula
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
        ctx.move_to(0, 112).text(formula.__name__)
        ctx.restore()


__app_export__ = Tixy

# ------------------------------ try this --------------------------------------
# - click ripple above, then nudge the 7.5 in ripple() (drag or tap): the splash follows
# - in waves(), change math.cos to math.sin -- then try math.tan (chaos)
# - add your own formula:  def stripes(t, i, x, y): return math.sin(x - t * 3)
#   then add a "# LIVE = stripes  #: stripes" line to the picker and click it
