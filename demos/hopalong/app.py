# hopalong (7) -- Hopalong plotter. One point hops by a fixed rule; a few thousand
# hops paint Barry Martin's strange attractor as a slowly turning cloud.
#
# HOW IT WORKS
#   A single point plays hopscotch. Each hop it looks at where it stands
#   (x, y) and at three fixed numbers a, b, c, then jumps:
#       new x = y - sign(x) * sqrt(|b*x - c|)        new y = a - x
#   No randomness anywhere -- yet the landing spots scatter into swirls and
#   petals nobody designed. We keep the last few hundred spots on screen,
#   colour them rainbow by age, and slowly spin the whole cloud.
#
# PRIOR ART  Barry Martin's Hopalong attractor, popularised by A. K. Dewdney in
#            Scientific American (Sept 1986) -- https://en.wikibooks.org/wiki/Fractals/Hopalong
#
# BUTTONS   RIGHT/LEFT next/previous preset (fresh cloud) - CANCEL exits
#
#   sim:   python3 demos/sim/run.py hopalong --gif
#   badge: drop demos/hopalong into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-click, or tap on a phone, for a slider);
# the "MIN<n<MAX" notes set each slider's range.
# Each preset row is (a, b, c, zoom). The attractor is touchy: nudge an a, b
# or c a little and a completely different creature grows in its place.
PRESETS = ((-2.0, 0.35, 1.2, 3.6),   # try dragging the 0.35 very slowly
           (2.1, 1.9, 0.5, 2.2),
           (-3.1, 0.2, 1.9, 2.6),
           (1.3, 1.3, 1.3, 3.0))
POINTS = 14       # 0<n<40   new hops per frame ...... try 30 (fills in faster)
KEEP = 440        # 0<n<600  spots kept on screen .... try 150 (wispy); each spot is a
                  #          draw call and ~500/frame is the badge's budget
SPIN = 0.15       # -1<n<1   cloud rotation speed .... try -0.15 (other way) or 0.6
ZOOM = 7.0        # 0<n<20   pixels per maths unit ... try 12.0 to fly in close
DOT = 1.6         # 0<n<6    size of each spot ....... try 3.0 (chunky stars)
HUE_DRIFT = 0.1   # 0<n<1    colour cycling speed .... 0.6 turns it into a disco

# ------------------------------- the hop -------------------------------------

def sign(v):
    # -1, 0 or +1: which side of zero v is on
    return 1.0 if v > 0 else (-1.0 if v < 0 else 0.0)


def hop(x, y, a, b, c):
    # Barry Martin's rule -- the next spot depends only on the current one
    return y - sign(x) * math.sqrt(abs(b * x - c)), a - x


def rainbow(h):
    # a number -> a colour around the colour wheel (only the fraction counts)
    h = h - int(h)
    i = int(h * 6)           # which sixth of the wheel we are in
    f = h * 6 - i            # how far into that sixth
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


class Hopalong(app.App):
    """Hop the point a few times per frame; draw the trail it leaves behind."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False       # have we taken the screen yet?
        self.t = 0.0          # seconds since start
        self.preset = 0       # which (a, b, c, zoom) row is live
        self.restart()

    def restart(self):
        # back to the origin with an empty trail -- new constants, new creature
        self.x = 0.0
        self.y = 0.0
        self.pts = []

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += delta / 1000.0
        buttons = self.button_states
        if buttons.get(BUTTON_TYPES["CANCEL"]):
            buttons.clear()
            self.minimise()
            return False
        if buttons.get(BUTTON_TYPES["RIGHT"]):
            buttons.clear()
            self.preset = (self.preset + 1) % len(PRESETS)
            self.restart()
        if buttons.get(BUTTON_TYPES["LEFT"]):
            buttons.clear()
            self.preset = (self.preset - 1) % len(PRESETS)
            self.restart()
        a, b, c, _ = PRESETS[self.preset % len(PRESETS)]
        x, y = self.x, self.y
        for _ in range(POINTS):
            x, y = hop(x, y, a, b, c)
            self.pts.append((x, y))
        self.x, self.y = x, y
        if len(self.pts) > KEEP:
            self.pts = self.pts[-KEEP:]      # forget the oldest hops
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        scale = PRESETS[self.preset % len(PRESETS)][3] * ZOOM
        ctx.rotate(self.t * SPIN)            # the whole cloud turns as one
        n = len(self.pts)
        base = self.t * HUE_DRIFT
        for idx in range(n):
            px, py = self.pts[idx]
            x = px * scale
            y = py * scale
            if x < -118 or x > 118 or y < -118 or y > 118:
                continue                     # off the glass -- skip it
            r, g, b = rainbow(base + idx * 0.0006)    # neighbours, kin hues
            ctx.rgba(r, g, b, 0.25 + 0.75 * (idx / n))  # newest spots glow
            ctx.rectangle(x, y, DOT, DOT).fill()
        ctx.restore()


__app_export__ = Hopalong

# ------------------------------ try this --------------------------------------
# - drag or tap the first preset's 0.35 up towards 1.0 in tiny steps and watch the
#   creature melt and re-grow a new shape at every stop
# - set SPIN to 0.0 and ZOOM to 12.0 for a still, close-up portrait
# - add a preset: put (1.1, 0.5, 1.0, 2.5) at the end of PRESETS, then press
#   RIGHT until it comes up -- it stays almost entirely on the glass
