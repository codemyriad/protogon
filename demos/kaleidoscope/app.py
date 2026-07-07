# kaleidoscope (6) -- Hex kaleidoscope. One tiny random doodle, stamped and mirrored
# N times around the centre -- instant snowflake.
#
# HOW IT WORKS
#   A real kaleidoscope holds just ONE pinch of coloured junk -- the mirrors
#   do everything else. Same trick here: each frame we draw one small doodle
#   (a spoke plus two drifting dots), rotate-stamp it N times around the
#   centre, and stamp a flipped twin each time so the wedges mirror like
#   glass. The doodle is random; the symmetry is what makes it beautiful.
#
# PRIOR ART  the kaleidoscope, invented by David Brewster in 1817 --
#            https://en.wikipedia.org/wiki/Kaleidoscope
#
# BUTTONS   CONFIRM new random doodle - RIGHT/LEFT change symmetry - CANCEL exits
#
#   sim:   python3 demos/sim/run.py kaleidoscope --gif
#   badge: drop demos/kaleidoscope into the official simulator's sim/apps/ (see README)
import app
import math
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
SYMMETRIES = (6, 8, 12)   # wedge counts RIGHT/LEFT step through . try (3, 5, 7)
WHIRL      = 0.2          # spin of the whole flake ....... try 1.0, or -0.4
HUE_DRIFT  = 0.05         # colours creep round the rainbow ... rush them: 0.40
SQUASH     = 0.5          # dot orbit shape: 1.0 round loop, 0.1 flat pancake
LINE_W     = 2.0          # spoke thickness ................... chunky: 6.0
ORBIT_MIN  = 30           # closest the big dot orbits ....... try 10
ORBIT_MAX  = 80           # furthest the big dot orbits ...... try 118 (wild)
SPIN_MIN   = 0.6          # slowest a reroll can spin ........ try 0.1 (lazy)
SPIN_MAX   = 2.2          # fastest a reroll can spin ........ try 5.0 (dizzy)
DOT_MIN    = 6            # smallest dot a reroll can pick ... try 12
DOT_MAX    = 16           # biggest dot a reroll can pick ..... 30, then CONFIRM
REACH_MIN  = 60           # shortest spoke a reroll can pick .. try 20
REACH_MAX  = 105          # longest spoke a reroll can pick ... 118 kisses the rim

TAU = 6.28318

# ---------------------------- a pocket rainbow --------------------------------

def rainbow(h):
    # hue 0..1 -> (r,g,b), walking the six edges of the colour wheel
    h = h - int(h)
    i = int(h * 6)
    f = h * 6 - i
    q = 1.0 - f
    if i == 0:
        return (1.0, f, 0.0)
    if i == 1:
        return (q, 1.0, 0.0)
    if i == 2:
        return (0.0, 1.0, f)
    if i == 3:
        return (0.0, q, 1.0)
    if i == 4:
        return (f, 0.0, 1.0)
    return (1.0, 0.0, q)


class Kaleidoscope(app.App):
    """Roll a random doodle, then let rotational symmetry do the beauty."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False      # have we taken the screen yet?
        self.t = 0.0         # seconds since start
        self.symi = 0        # which entry of SYMMETRIES is live
        self.reseed()

    def reseed(self):
        # roll a fresh doodle: how far the big dot orbits, how fast, how big
        self.orbit = random.uniform(ORBIT_MIN, ORBIT_MAX)
        self.spin = random.uniform(SPIN_MIN, SPIN_MAX) * random.choice((-1, 1))
        self.dot = random.uniform(DOT_MIN, DOT_MAX)
        self.hue = random.random()
        self.reach = random.uniform(REACH_MIN, REACH_MAX)

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
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self.reseed()
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.symi = (self.symi + 1) % len(SYMMETRIES)
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.symi = (self.symi - 1) % len(SYMMETRIES)
        return True

    def motif(self, ctx):
        # the ONE doodle everything is made of: a spoke and two riding dots
        angle = self.t * self.spin
        ox = math.cos(angle) * self.orbit           # the big dot rides an oval
        oy = math.sin(angle) * self.orbit * SQUASH
        r, g, b = rainbow(self.hue + self.t * HUE_DRIFT)
        ctx.line_width = LINE_W
        ctx.rgba(r, g, b, 0.9)
        ctx.move_to(0, 0).line_to(self.reach, 0).stroke()
        ctx.rgba(b, r, g, 0.85)   # same rainbow, channels shuffled: free harmony
        ctx.arc(ox, oy, self.dot, 0, TAU, True).fill()
        ctx.rgba(g, b, r, 0.6)
        ctx.arc(self.reach * 0.7,   # little dot sits 70% of the way out...
                6,                  # ...and 6 px off the spoke, so mirrors show
                self.dot * 0.5, 0, TAU, True).fill()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        sym = SYMMETRIES[self.symi % len(SYMMETRIES)]
        ctx.rotate(self.t * WHIRL)         # the whole flake turns, slowly
        for s in range(sym):
            ctx.save()
            ctx.rotate(TAU * s / sym)      # swing round to this wedge...
            self.motif(ctx)                # ...stamp the doodle...
            ctx.scale(1.0, -1.0)           # ...flip it like a mirror...
            self.motif(ctx)                # ...and stamp its twin
            ctx.restore()
        ctx.restore()


__app_export__ = Kaleidoscope

# ------------------------------ try this --------------------------------------
# - drag the 12 in SYMMETRIES up to 24, press RIGHT until it's live: lace doily
# - set WHIRL to -0.4 and SQUASH to 1.0 -- reverse spin, perfectly round orbits
# - in motif(), change line_to(self.reach, 0) to line_to(self.reach, 40):
#   every spoke bends, and the mirrors fold the bends into zigzag stars
