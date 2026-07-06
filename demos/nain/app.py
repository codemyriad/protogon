# nain (9) -- Plasma tiles. Four drifting sine waves add up to paint a 16x16
# tile grid -- the classic demoscene plasma, no per-pixel framebuffer needed.
#
# HOW IT WORKS
#   Every frame, each tile asks one question: "how hot am I right now?"
#   The answer is four sine waves added together: one runs across the
#   screen, one runs down, one slants diagonally, one ripples out from the
#   centre. Where crests pile up a tile glows hot; where waves cancel it
#   goes cold. A palette turns hot-and-cold into colour -- that's plasma.
#
# BUTTONS   LEFT/RIGHT swap palette - CANCEL exits
#
#   sim:   python3 demos/sim/run.py nain --gif
#   badge: drop demos/nain into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
GRID      = 16               # tiles per side .. try 8 (chunky); 24 chugs the badge
SPEED     = 1.0              # animation speed ......... 0.3 lava lamp, 3.0 boiling
WAVE_X    = 0.6              # across-the-screen wave .. drag slowly: bands stretch
WAVE_Y    = 0.7              # down-the-screen wave .... try 0.0 -- it goes flat
WAVE_DIAG = 0.45             # diagonal wave ........... try 1.5: slanted stripes
RIPPLE    = 0.7              # rings from the centre ... try 2.0: tight bullseye
OCEAN     = (0.0, 0.3, 0.5)  # deepest water in the ocean palette (press RIGHT)

TILE = 240.0 / max(GRID, 1)  # px per tile (max() survives a drag to zero)
CENTRE = (GRID - 1) / 2.0    # the spot the ripple wave spreads from

# ------------------------------ the plasma -----------------------------------
# fx/fy = how far this tile sits from the centre of the grid.

def heat(fx, fy, t):
    # four waves, each wandering at its own pace
    # (the 1.1 / 0.7 / 1.7 are those paces -- fun to drag)
    across = math.sin(fx * WAVE_X + t)
    down = math.sin(fy * WAVE_Y - t * 1.1)
    diag = math.sin((fx + fy) * WAVE_DIAG + t * 0.7)
    rings = math.sin(((fx * fx + fy * fy) ** 0.5) * RIPPLE - t * 1.7)
    # each wave is -1..1, so the sum is -4..4 -> squeeze it into 0..1
    return (across + down + diag + rings + 4.0) / 8.0

# ----------------------------- the palettes ----------------------------------
# A palette turns heat (0 = coldest, 1 = hottest) into a colour. Add your own.

def fire(v):
    # embers: red wakes up first, green joins later (making orange), blue barely
    return (v * 1.6, v * 1.4 - 0.4, v * 0.6 - 0.4)

def ocean(v):
    # deep water rising to pale foam; OCEAN above sets the darkest shade
    return (OCEAN[0] + v * 0.2, OCEAN[1] + v * 0.6, OCEAN[2] + v * 0.5)

def rainbow(v):
    # three sines a third of a turn apart walk the whole colour wheel
    a = v * 6.28318
    return (0.5 + 0.5 * math.sin(a),
            0.5 + 0.5 * math.sin(a + 2.09),
            0.5 + 0.5 * math.sin(a + 4.19))

PALETTES = (fire, ocean, rainbow)


class Nain(app.App):
    """Keep time, listen for palette swaps, paint the tile grid."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.t = 0.0           # plasma clock, in seconds
        self.pal = 0           # which palette is live

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
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.pal = (self.pal + 1) % len(PALETTES)
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        palette = PALETTES[self.pal % len(PALETTES)]
        t = self.t
        for gy in range(GRID):
            y = -120 + gy * TILE
            fy = gy - CENTRE
            for gx in range(GRID):
                r, g, bl = palette(heat(gx - CENTRE, fy, t))
                # clamp to 0..1 -- fire runs past the ends on purpose,
                # and real badge glass does strange things beyond 1.0
                ctx.rgb(max(0.0, min(1.0, r)),
                        max(0.0, min(1.0, g)),
                        max(0.0, min(1.0, bl)))
                # +0.6 makes each tile overlap a hair, hiding hairline seams
                ctx.rectangle(-120 + gx * TILE, y, TILE + 0.6, TILE + 0.6).fill()
        ctx.restore()


__app_export__ = Nain

# ------------------------------ try this --------------------------------------
# - set WAVE_X, WAVE_Y and WAVE_DIAG all to 0.0: the sliding waves go flat and
#   a pure bullseye is left pulsing out of the centre
# - in heat(), drag the rings wave's 1.7 down to 0.0 -- the rings freeze in
#   place while the other three waves keep sliding through them
# - add a palette:  def mint(v): return (v * 0.3, v, v * 0.7)
#   then put it in PALETTES and press RIGHT until the screen turns minty
