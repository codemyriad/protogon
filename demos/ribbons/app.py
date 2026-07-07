# ribbons (13) -- Drift lines. Wavy anchor points threaded into smooth spline
# ribbons; a few phase-shifted copies braid together.
#
# HOW IT WORKS
#   A ribbon is really just a few invisible anchor points spread left to
#   right. Every frame each anchor rides two sine waves added together --
#   one big slow swing plus a gentler wobble -- so it drifts like seaweed.
#   Then a smooth curve is threaded through them: quad_to bends TOWARD each
#   anchor and glides through the midpoint beyond it, the classic trick for
#   a spline with no kinks. Copies with the wave shifted along braid together.
#
# PRIOR ART  in the spirit of the old "Mystify" screensaver -- https://en.wikipedia.org/wiki/Mystify
#
# BUTTONS   RIGHT/LEFT change how many ribbons braid - CANCEL exits
#
#   sim:   python3 demos/sim/run.py ribbons --gif
#   badge: drop demos/ribbons into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-tap for a slider on a touchscreen);
# the "MIN<n<MAX" notes set each slider's range.
RIBBONS    = 3      # 1<n<12   ribbons in the braid (RIGHT/LEFT change this too).. try 6
R_MIN, R_MAX = 2, 6  # 1<a<12  1<b<12  ribbon-count range RIGHT/LEFT walks .. try 1, 9
ANCHORS    = 7      # 2<n<16   anchor points per ribbon ........ try 4 (angular) or 12
SWAY       = 70.0   # 0<n<160  how far anchors swing up and down, px ........ try 110.0
SWAY_SPEED = 0.8    # 0<n<4    speed of the big swing ............... try 2.0 (frantic)
WOBBLE     = 20.0   # 0<n<80   the slower second wave stacked on top ........ try 45.0
THICKNESS  = 2.5    # 0<n<12   ribbon stroke width, px ............... try 6.0 (chunky)
GLOW       = 0.85   # 0<n<1    ribbon opacity, 0..1 .................. try 0.40 (misty)
PALETTE    = ((0.3, 0.8, 1.0), (1.0, 0.4, 0.7), (0.6, 1.0, 0.5),
              (1.0, 0.8, 0.3), (0.7, 0.5, 1.0))  # sky, pink, mint, gold, lilac

SPAN = 216.0 / max(1, ANCHORS - 1)   # px between anchors -- fills the screen

# ------------------------------ the drift ------------------------------------

def anchor_points(t, phase):
    # Where are this ribbon's anchor points right now?
    pts = []
    for i in range(ANCHORS):
        # 0.9 = how much the wave twists between neighbouring anchors
        y = (math.sin(t * SWAY_SPEED + i * 0.9 + phase) * SWAY
             + math.sin(t * 0.35 + i) * WOBBLE)
        # plus a little sideways sway (12 px) so the spacing breathes too
        x = -108 + i * SPAN + math.cos(t * 0.5 + i * 1.3 + phase) * 12
        pts.append((x, y))
    return pts


class Ribbons(app.App):
    """Keep time, listen to buttons, drift the anchors, thread the ribbons."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False    # have we taken the screen yet?
        self.t = 0.0       # seconds since start
        self.shift = 0     # how far the buttons have walked from RIBBONS

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
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.shift += 2    # striding by 2 still visits every count 2..6
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.shift -= 2
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        # the button offset wraps so the braid always has R_MIN..R_MAX ribbons
        count = R_MIN + (RIBBONS - R_MIN + self.shift) % (R_MAX - R_MIN + 1)
        ctx.line_width = THICKNESS
        for r in range(count):
            phase = r * (6.28318 / count)   # spread the copies round the wave
            pts = anchor_points(self.t, phase)
            colour = PALETTE[r % len(PALETTE)]
            ctx.rgba(colour[0], colour[1], colour[2], GLOW)
            ctx.move_to(pts[0][0], pts[0][1])
            for i in range(1, ANCHORS - 1):
                # bend toward this anchor, glide through the next midpoint
                mid_x = (pts[i][0] + pts[i + 1][0]) / 2.0
                mid_y = (pts[i][1] + pts[i + 1][1]) / 2.0
                ctx.quad_to(pts[i][0], pts[i][1], mid_x, mid_y)
            ctx.line_to(pts[ANCHORS - 1][0], pts[ANCHORS - 1][1])
            ctx.stroke()
        ctx.restore()


__app_export__ = Ribbons

# ------------------------------ try this --------------------------------------
# - drag / double-tap SWAY to 110.0 and THICKNESS to 6.0 -- fat ribbons that fill the badge
# - set WOBBLE to 0.0 for one clean repeating braid, then ease it back up and
#   watch the pattern loosen into drift
# - the 0.9 in anchor_points() is the twist between neighbours: try 0.1 (lazy
#   arcs) or 3.0 (scribbles)
