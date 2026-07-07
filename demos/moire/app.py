# moire (2) -- Moire rings. Two families of thin rings drift past each other with
# a slight phase mismatch; the interference does the work, not the code.
#
# HOW IT WORKS
#   Draw one family of thin rings. Draw a second, identical family, mirrored
#   through the middle of the screen. Each family is boring on its own -- but
#   where the two overlap, their lines almost-but-not-quite line up, and your
#   eye invents big swirling curves nobody actually drew. That ghost pattern
#   is a moire: you've seen it where two fences overlap, or when a striped
#   shirt shimmers on TV.
#
# BUTTONS   RIGHT or LEFT swap circles <-> hexagons - CANCEL exits
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-click, or tap on a phone, for a slider);
# the "MIN<n<MAX" notes set each slider's range.
RINGS    = 11                  # 4<n<24   rings per family ....... try 6 (airy) or 16
RING_GAP = 8.0                 # 2<n<16   px between ring radii .. squeeze them: 5.0
INNER    = 14                  # 0<n<40   innermost ring radius . try 30 (big hole)
DRIFT    = 30.0                # 0<n<100  how far a family wanders off-centre.. try 70.0
SPEED    = 1.0                 # 0<n<5    drift speed ............ try 3.0 (dizzy)
STAGGER  = 0.30                # 0<n<1    wander delay, ring to ring.. try 0.0 or 0.9
SIDES    = 6                   # 3<n<12   corners in hexagon mode.. try 3 (triangles)
LINE_W   = 1.6                 # 0<n<6    line thickness, px .... thin best: 3.0
CYAN     = (0.15, 0.75, 1.0)   # first family's colour -- tap the swatch
PINK     = (1.0, 0.25, 0.55)   # second family's colour (the mirror twin)

# ------------------------------ ring shapes ----------------------------------

def circle_ring(ctx, cx, cy, radius):
    # one thin circle outline
    ctx.arc(cx, cy, radius, 0, 6.2832, True).stroke()


def polygon_ring(ctx, cx, cy, radius, spin):
    # walk SIDES corners around the centre and join the dots
    step = 6.2832 / SIDES
    ctx.begin_path()
    for corner in range(SIDES + 1):
        angle = spin + corner * step
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        if corner == 0:
            ctx.move_to(x, y)
        else:
            ctx.line_to(x, y)
    ctx.stroke()


class Moire(app.App):
    """Keep time, flip shapes on RIGHT, draw the two mirrored ring families."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # the one clock everything drifts by
        self.hexed = False     # False = circles, True = polygons

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += (delta / 1500.0) * SPEED
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.hexed = not self.hexed
        return True

    def ring(self, ctx, cx, cy, radius, spin):
        # one ring, drawn as whichever shape RIGHT has picked
        if self.hexed:
            polygon_ring(ctx, cx, cy, radius, spin)
        else:
            circle_ring(ctx, cx, cy, radius)

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = LINE_W           # thin lines moire best
        t = self.t
        spin = t * 0.4                    # how fast the hexagons rotate
        for k in range(RINGS):
            # each ring's centre wanders its own loopy path; STAGGER makes
            # ring k lag ring k-1 a little, so the family stretches and folds
            wobble = t + k * STAGGER
            ox = math.sin(wobble) * DRIFT
            oy = math.cos(wobble * 1.3) * DRIFT   # 1.3 = loopy, 1.0 = round
            radius = INNER + k * RING_GAP         # the innermost ring
            # family one: cool, outer rings a shade warmer to hint at depth
            ctx.rgba(CYAN[0] + 0.05 * k, CYAN[1], CYAN[2], 0.42)
            self.ring(ctx, ox, oy, radius, spin)
            # family two: warm, at the exact mirror spot, spinning backwards
            ctx.rgba(PINK[0], PINK[1] + 0.04 * k, PINK[2], 0.40)
            self.ring(ctx, -ox, -oy, radius, -spin)
        ctx.restore()


__app_export__ = Moire

# ------------------------------ try this --------------------------------------
# - set STAGGER to 0.0: each family snaps into a rigid bullseye, and you get
#   two targets orbiting each other instead of a swirling interference cloud
# - drag or tap the 1.3 in the wander line to 1.0 -- every centre now travels a
#   perfect circle, so the whole pattern stops morphing and just spins
# - press RIGHT for polygons, then drag or tap SIDES down to 3: drifting triangle
#   moire (4 gives diamonds, 12 is nearly circles again)
