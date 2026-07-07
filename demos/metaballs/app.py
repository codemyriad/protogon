# metaballs (14) -- Orbiting metaballs (lite). Glowing blobs circle the centre
# and seem to melt together wherever their halos overlap.
#
# HOW IT WORKS
#   Real metaballs measure a "goo field" at every pixel -- far too slow here.
#   The trick: each blob is just a stack of see-through discs, small and
#   bright in the middle, big and faint at the edge. Translucent colour piles
#   up where discs overlap, so when two blobs drift close their halos build a
#   bright bridge between them -- your eye reads it as goo merging.
#   Each blob follows its own slightly detuned orbit, so they keep meeting.
#
# PRIOR ART  metaballs, invented by Jim Blinn for Carl Sagan's Cosmos --
#            https://en.wikipedia.org/wiki/Metaballs
#
# BUTTONS   RIGHT/LEFT change blob count (3-5) - CANCEL exits
#
#   sim:   python3 demos/sim/run.py metaballs --gif
#   badge: drop demos/metaballs into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

TAU = 6.28318

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-tap for a slider on a touchscreen);
# the "MIN<n<MAX" notes set each slider's range.
SPEED   = 1.0    # 0<n<5    pace of the whole dance ...... try 0.3 (lava lamp) or 2.5
ORBIT   = 40     # 0<n<120  average orbit radius, px ..... try 70 (blobs hug the rim)
SWAY    = 18     # 0<n<80   how far orbits breathe .......... try 60 (wild dives)
SIZE    = 46     # 0<n<100  blob radius, px ................. try 65 (one big glob)
LAYERS  = 5      # 1<n<12   discs per blob .................. try 2 (flat) or 8 (silky)
HAZE    = 0.12   # 0<n<1    alpha of the outermost halo ..... try 0.30 (foggy)
GLOW    = 0.26   # 0<n<1    extra alpha at the core ......... try 0.45 (hot centres)
PALETTE = ((1.0, 0.3, 0.3), (0.3, 0.6, 1.0), (0.4, 1.0, 0.5),
           (1.0, 0.8, 0.2), (0.9, 0.4, 1.0))   # one colour per blob

# ------------------------------ one blob --------------------------------------

def draw_blob(ctx, x, y, colour):
    # paint the stack core-first: each later disc is bigger and fainter,
    # so the blob fades out smoothly instead of ending at a hard edge
    for layer in range(LAYERS):
        heat = (LAYERS - layer) / LAYERS       # 1.0 at the core, ~0 outside
        radius = SIZE * (0.25 + 0.75 * (layer + 1) / LAYERS)
        ctx.rgba(colour[0], colour[1], colour[2], HAZE + GLOW * heat)
        ctx.arc(x, y, radius, 0, TAU, True).fill()


class Metaballs(app.App):
    """Move each blob along its wobbly orbit, then paint the disc stacks."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # seconds since start, scaled by SPEED
        self.count = 3         # blobs on screen (RIGHT/LEFT cycle 3-5)

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        self.t += (delta / 1000.0) * SPEED
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.count = 3 + self.count % 3          # 3 -> 4 -> 5 -> 3
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.count = 3 + (self.count - 1) % 3    # 3 -> 5 -> 4 -> 3
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        t = self.t
        for k in range(self.count):
            # spread the blobs evenly round the circle to start with...
            start = k * (TAU / self.count)
            # ...then let each orbit breathe in and out at its own moment
            orbit = ORBIT + SWAY * math.sin(t * 0.5 + k)
            # 0.12 and 0.1 detune each blob's tempo -- drag them toward 0
            # and the blobs fall into formation; bigger and they scatter
            x = math.cos(t * (0.6 + 0.12 * k) + start) * orbit
            y = math.sin(t * (0.5 + 0.1 * k) + start) * orbit * 0.9
            draw_blob(ctx, x, y, PALETTE[k % len(PALETTE)])
        ctx.restore()


__app_export__ = Metaballs

# ------------------------------ try this --------------------------------------
# - drag / double-tap SWAY up to 60: the blobs dive right through the middle and pile
#   into one white-hot blaze every time they cross
# - set LAYERS to 1 -- suddenly it's just flat circles. The whole metaball
#   illusion lives in that stack of fading discs
# - drag / double-tap the 0.9 at the end of the y line down to 0.3 and the dance
#   flattens into a shallow band, like blobs on a horizon
