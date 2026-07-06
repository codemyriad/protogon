# tri (3) -- Qix tracer. Bouncing points drag fading afterimages behind them.
#
# HOW IT WORKS
#   A few points fly around, bouncing off the walls of an invisible box.
#   Every frame we join them into one closed shape and remember it, then
#   draw the last TRAIL shapes oldest first -- old ones faint and thin,
#   new ones bright and thick. No blur trick: the trail is just yesterday's
#   shapes politely fading away. The 12 LED ring breathes the head colour.
#
# BUTTONS   CONFIRM add a point (2->3->4) - RIGHT/LEFT palette - CANCEL exits
#
#   sim:   python3 demos/sim/run.py tri --gif
#   badge: drop demos/tri into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
TRAIL     = 42                 # shapes remembered ....... try 12 (crisp) or 80
BOX       = 106                # half-width of the bounce box ... squeeze to 60
SPEED_MIN = 70.0               # slowest fresh point, pixels per second
SPEED_MAX = 110.0              # fastest fresh point ..... try 300.0 (frantic)
RAINBOW   = 0.15               # hue turns per second in rainbow mode: try 0.5
EMBER     = (1.0, 0.4, 0.1)    # second palette: glowing coals
ICE       = (0.3, 0.9, 1.0)    # third palette: cold blue


def hue(h):
    # walk the colour wheel: 0..1 goes red -> yellow -> green -> blue -> red
    h = (h - int(h)) * 6.0     # which of the six rainbow segments we are in
    i = int(h)
    f = h - i                  # how far into that segment, 0..1
    return ((1.0, f, 0.0), (1.0 - f, 1.0, 0.0), (0.0, 1.0, f),
            (0.0, 1.0 - f, 1.0), (f, 0.0, 1.0), (1.0, 0.0, 1.0 - f))[i % 6]


class Tri(app.App):
    """Move the points, remember their shape, draw the memories fading."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False          # have we taken the screen and LEDs yet?
        self.t = 0.0             # seconds since start
        self.npts = 3            # how many points are bouncing (2..4)
        self.palette = 0         # 0 rainbow, 1 ember, 2 ice
        self.respawn()

    def respawn(self):
        # throw self.npts fresh points into the box, each flying its own way
        import random
        self.pts = []
        for _ in range(self.npts):
            ang = random.uniform(0, 6.28)
            speed = random.uniform(SPEED_MIN, SPEED_MAX)
            self.pts.append([random.uniform(-BOX, BOX),
                             random.uniform(-BOX, BOX),
                             math.cos(ang) * speed, math.sin(ang) * speed])
        self.trail = []          # remembered shapes; each = a list of (x, y)

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())      # borrow the LED ring
            self.fg = True
        dt = delta / 1000.0
        self.t += dt
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())       # hand the ring back
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self.npts = 2 + (self.npts - 1) % 3  # 2 -> 3 -> 4 -> back to 2
            self.respawn()
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.palette = (self.palette + 1) % 3
        for p in self.pts:                       # p = [x, y, vx, vy]
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[0] < -BOX or p[0] > BOX:        # hit a side wall: bounce
                p[2], p[0] = -p[2], max(-BOX, min(BOX, p[0]))
            if p[1] < -BOX or p[1] > BOX:        # hit the floor or ceiling
                p[3], p[1] = -p[3], max(-BOX, min(BOX, p[1]))
        # remember today's shape, forget the oldest one
        self.trail.append([(p[0], p[1]) for p in self.pts])
        if len(self.trail) > TRAIL:
            self.trail.pop(0)
        self.light_ring()
        return True

    def head_colour(self):
        # palette 0 drifts around the rainbow; the others hold one mood
        if self.palette == 0:
            return hue((self.t * RAINBOW) % 1.0)
        if self.palette == 1:
            return EMBER
        return ICE

    def light_ring(self):
        # the LEDs breathe the head colour, a slow wave chasing round the ring
        r, g, bl = self.head_colour()
        base = self.t * 2.0                      # wave speed -- drag me
        for i in range(1, 13):
            glow = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(base + i * 0.52))
            tildagonos.leds[i] = (int(r * 255 * glow), int(g * 255 * glow),
                                  int(bl * 255 * glow))
        tildagonos.leds.write()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        n = len(self.trail)
        hr, hg, hb = self.head_colour()
        for idx in range(n):
            shape = self.trail[idx]
            age = (idx + 1) / n              # 0 = oldest memory, 1 = right now
            ctx.line_width = 1.0 + 2.0 * age
            ctx.rgba(hr, hg, hb, age * age * 0.9)   # squared: old dies faster
            hx, hy = shape[0]
            ctx.move_to(hx, hy)
            for (x, y) in shape[1:]:
                ctx.line_to(x, y)
            ctx.line_to(hx, hy)              # come back home: a closed loop
            ctx.stroke()
        ctx.rgb(1, 1, 1)                     # bright white heads mark "now"
        for (x, y) in self.trail[-1] if self.trail else []:
            ctx.arc(x, y, 3, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Tri

# ------------------------------ try this --------------------------------------
# - drag TRAIL to 80 and SPEED_MAX to 300.0 -- long ribbons whip around the box
# - squeeze BOX down to 40: the whole dance folds into a knot mid-screen
# - in draw(), change  age * age * 0.9  to  age * 0.9  for a gentler, even fade
