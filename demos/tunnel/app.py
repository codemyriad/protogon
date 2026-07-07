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
# BUTTONS   LEFT/RIGHT cycle colour scheme - CANCEL exits
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-click, or tap on a phone, for a slider);
# the "MIN<n<MAX" notes set each slider's range.
RINGS    = 22     # 6<n<40   rings in the stack.. 10 = sparse, 34 = dense
INNER    = 6.0    # 2<n<24   radius of the smallest ring.. bigger opens the mouth
RING_GAP = 5.2    # 2<n<10   px from one ring to the next
BREATH   = 3.0    # -6<n<8   how fast the bright band rolls (negative = inward)
RIPPLE   = 0.55   # 0<n<2    wave crowding: bigger squeezes more bands in
WANDER   = 12.0   # 0<n<40   how far the tunnel mouth drifts.. 30 gets seasick

# --------------------------- pick the colours --------------------------------
# Click a scheme to switch it live (on a real badge, LEFT/RIGHT cycle them).
# Each is a tint -- how much of each channel a ring keeps. Every value is
# 0..1, so its swatch opens a colour picker; BOOST lets a channel hit full
# blast a little before the wave peaks (that's what gives fire its glow).
TINT = (0.8, 0.85, 1.0)     #: moonlight
# TINT = (1.0, 0.45, 0.1)   #: fire
# TINT = (0.2, 0.7, 1.0)    #: ice
# TINT = (1.0, 0.25, 1.0)   #: magenta
BOOST = 1.35      # >1 = channels saturate early (brighter, punchier).. try 1.0

PALETTE = ((0.8, 0.85, 1.0), (1.0, 0.45, 0.1),
           (0.2, 0.7, 1.0), (1.0, 0.25, 1.0))   # what LEFT/RIGHT cycle

TAU = 6.28318


def tinted(glow, tint):
    # this ring's brightness times the scheme's tint (and BOOST), capped at full
    g = glow * BOOST
    return (min(1.0, g * tint[0]),
            min(1.0, g * tint[1]),
            min(1.0, g * tint[2]))


class Tunnel(app.App):
    # Keep time, cycle colour schemes, draw the breathing ring stack.

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # seconds since start
        self.tint = TINT       # the live tint (set by the picker above)

    # Carry time across live edits, not the tint: clicking a scheme swaps it in.
    __live_state__ = ("t",)

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
            here = PALETTE.index(self.tint) if self.tint in PALETTE else 0
            self.tint = PALETTE[(here + 1) % len(PALETTE)]
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        # the tunnel mouth wanders in a slow loop -- two sines at slightly
        # different speeds, so the path never quite repeats itself
        ox = math.sin(t * 0.7) * WANDER
        oy = math.cos(t * 0.9) * WANDER
        tint = self.tint
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
# - click a scheme above, then click its colour swatch to invent your own tint
