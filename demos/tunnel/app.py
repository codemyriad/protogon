# tunnel (5) -- Polar tunnel. A stack of concentric rings breathes and drifts
# until flat circles read as a 3D tunnel you are flying down.
#
# HOW IT WORKS
#   Every frame each ring asks one question: "how bright am I right now?"
#   The answer is a sine wave that travels outward along the stack, so a
#   band of bright, fat rings keeps rolling past you -- that reads as
#   forward motion. The depth trick: the whole stack drifts off centre,
#   but the small far-away rings drift the most while the big nearest
#   ring barely moves. Your brain sees that mismatch and says "tunnel".
#
# PRIOR ART  the demoscene tunnel effect -- https://en.wikipedia.org/wiki/Demo_effect
#
# BUTTONS   LEFT/RIGHT cycle colour scheme - CANCEL exits
#
#   sim:   python3 demos/sim/run.py tunnel --gif
#   badge: drop demos/tunnel into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
RINGS    = 22     # rings in the stack ........ try 10 (sparse) or 34 (dense)
INNER    = 6.0    # radius of the smallest ring.. 20.0 opens the mouth wide
RING_GAP = 5.2    # px from one ring to the next.. 8.0 stretches the tunnel
BREATH   = 3.0    # how fast the bright band rolls outward.. try 6.0 or 0.8
RIPPLE   = 0.55   # wave crowding: bigger squeezes more bands in.. try 1.6
WANDER   = 12.0   # how far the tunnel mouth drifts ........ 30.0 gets seasick

# Each scheme is a tint: how much of the brightness each channel keeps.
# (Values over 1.0 make that channel hit full blast early.)
SCHEMES = (
    (1.0, 1.0, 1.1),     # moonlight -- white with a cold blue edge
    (1.4, 0.6, 0.15),    # fire
    (0.2, 0.8, 1.3),     # ice
)

TAU = 6.28318


def tinted(glow, tint):
    # this ring's brightness times the scheme's tint, capped at full
    return (min(1.0, glow * tint[0]),
            min(1.0, glow * tint[1]),
            min(1.0, glow * tint[2]))


class Tunnel(app.App):
    """Keep time, cycle colour schemes, draw the breathing ring stack."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # seconds since start
        self.scheme = 0        # which tint is live

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
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.scheme = (self.scheme + 1) % len(SCHEMES)
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        # the tunnel mouth wanders in a slow loop -- two sines at slightly
        # different speeds, so the path never quite repeats itself
        ox = math.sin(t * 0.7) * WANDER
        oy = math.cos(t * 0.9) * WANDER
        tint = SCHEMES[self.scheme % len(SCHEMES)]
        for k in range(RINGS):
            # this ring's point on the wave rolling outward along the stack
            glow = 0.5 + 0.5 * math.sin(k * RIPPLE - t * BREATH)
            glow = glow * glow            # squaring dims the dim -> contrast
            cr, cg, cb = tinted(glow, tint)
            ctx.line_width = 2.0 + glow * 4.0   # bright rings get fat
            # parallax: far (small) rings take the full wobble, the nearest
            # almost none -- k/RINGS says how near this ring is
            depth = k / RINGS
            ctx.rgba(cr, cg, cb, 0.5 + 0.5 * glow)  # dim rings go sheer too
            ctx.arc(ox * (1 - depth), oy * (1 - depth),
                    INNER + k * RING_GAP, 0, TAU, True).stroke()
        ctx.restore()


__app_export__ = Tunnel

# ------------------------------ try this --------------------------------------
# - set WANDER to 0.0 -- the drift stops and you get pure breathing rings
# - make BREATH negative (-3.0): the wave rolls inward and the tunnel
#   swallows you instead of spitting you out
# - add a scheme: put (1.2, 0.3, 1.2) at the end of SCHEMES (magenta) and
#   press RIGHT until it comes up
