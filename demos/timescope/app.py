# timescope (15) -- A multiplication circle. One number slowly changes; the
# straight chords inside the circle fold into cardioids, flowers and knots.
#
# HOW IT WORKS
#   Put N pins around a clock face. For each pin i, draw a line from i to
#   i * MULTIPLIER, wrapping around when it passes N. When MULTIPLIER is 2,
#   this is the 2-times table; 3 is the 3-times table. Sliding between them
#   makes the familiar maths shape-bend into something that feels alive.
#
# BUTTONS   LEFT/RIGHT jump table - UP/DOWN speed - CONFIRM dot count - CANCEL exits
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

# ------------------------------ tweak me -------------------------------------
DOTS    = (72, 108, 144)          # pins around the circle; 144 is still badge-kind
SPEEDS  = (0.0, 0.16, 0.36, 0.72) # multiplier change per second; 0.0 = pause
RADIUS  = 104.0                   # chord endpoints sit just inside the round crop
ECHOES  = (0.18, 0.07, 0.0)       # draw older multipliers too: instant motion trail
TAU     = 6.2831853


def hue(h):
    # 0..1 around the colour wheel: red -> yellow -> green -> blue -> red
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    return ((1.0, f, 0.0), (1.0 - f, 1.0, 0.0), (0.0, 1.0, f),
            (0.0, 1.0 - f, 1.0), (f, 0.0, 1.0), (1.0, 0.0, 1.0 - f))[i % 6]


def point(turns, radius=RADIUS):
    a = turns * TAU
    return math.cos(a) * radius, math.sin(a) * radius


class Timescope(app.App):
    """Animate a times-table circle and mirror it on the 12 LEDs."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0              # added to the multiplier
        self.shift = 0.0          # button jumps between exact integer tables
        self.dot_mode = 1         # DOTS[1] = 108
        self.speed_mode = 1       # SPEEDS[1] = slow drift
        self.rebuild()

    def rebuild(self):
        n = DOTS[self.dot_mode]
        self.pins = [point(i / n) for i in range(n)]
        self.dot_step = max(1, n // 72)  # draw at most 72 little rim dots

    def multiplier(self):
        return 2.0 + self.shift + self.t

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())      # borrow the LED ring
            self.fg = True

        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())       # hand the ring back
            self.minimise()
            return False

        if b.get(BUTTON_TYPES["RIGHT"]):
            b.clear()
            self.shift += 1.0                    # next exact times table
            self.t = 0.0
        if b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.shift -= 1.0                    # previous exact times table
            self.t = 0.0
        if b.get(BUTTON_TYPES["UP"]):
            b.clear()
            self.speed_mode = min(len(SPEEDS) - 1, self.speed_mode + 1)
        if b.get(BUTTON_TYPES["DOWN"]):
            b.clear()
            self.speed_mode = max(0, self.speed_mode - 1)
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self.dot_mode = (self.dot_mode + 1) % len(DOTS)
            self.rebuild()

        self.t += delta / 1000.0 * SPEEDS[self.speed_mode]
        self.light_ring()
        return True

    def light_ring(self):
        m = self.multiplier()
        for i in range(1, 13):
            glow = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(m * TAU + i * 0.65))
            glow = glow * glow
            r, g, b = hue(i / 12 + m * 0.04)
            tildagonos.leds[i] = (int(r * 255 * glow),
                                  int(g * 255 * glow),
                                  int(b * 255 * glow))
        tildagonos.leds.write()

    def draw_chords(self, ctx, multiplier, alpha, width):
        n = len(self.pins)
        ctx.line_width = width
        for i in range(n):
            x1, y1 = self.pins[i]
            x2, y2 = point(((i * multiplier) % n) / n)
            r, g, b = hue(i / n + multiplier * 0.03)
            ctx.rgba(r, g, b, alpha)
            ctx.move_to(x1, y1).line_to(x2, y2).stroke()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()

        m = self.multiplier()
        ctx.line_width = 1.0
        ctx.rgba(0.12, 0.12, 0.16, 1.0).arc(0, 0, RADIUS, 0, TAU, True).stroke()

        for e, lag in enumerate(ECHOES):
            age = (e + 1) / len(ECHOES)
            self.draw_chords(ctx, m - lag, 0.09 + 0.32 * age * age, 0.55 + age)

        for i in range(0, len(self.pins), self.dot_step):
            r, g, b = hue(i / len(self.pins) + m * 0.03)
            ctx.rgba(r, g, b, 0.85)
            ctx.arc(self.pins[i][0], self.pins[i][1], 1.7, 0, TAU, True).fill()

        ctx.rgb(0.72, 0.72, 0.78)
        ctx.font_size = 16
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 112).text("%d pins  x %.2f" % (len(self.pins), m))
        ctx.restore()


__app_export__ = Timescope

# ------------------------------ try this --------------------------------------
# - press DOWN until speed is zero, then RIGHT one click at a time: 2x, 3x, 4x...
# - set DOTS to (12, 24, 144): the first two make the "clock face" idea obvious
# - remove two entries from ECHOES for a clean maths-diagram look
