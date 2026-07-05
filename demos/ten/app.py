# ten (10) -- LED / display phase-lock. The 12 dots on screen are drawn at the
# same angles as the 12 physical ring LEDs, and both are driven from ONE phase,
# so the glass and the bezel animate in lockstep. RIGHT cycles comet/pulse/
# rainbow, CANCEL exits (and hands the ring back to the system pattern service).
#
#   sim: python3 demos/sim/run.py ten --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

TAU = 6.28318
RING = 88                       # on-screen ring radius


def _hue(h):
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


def _ang(i):                    # i = 0..11, LED 1 at the top, clockwise
    return -math.pi / 2 + i * (TAU / 12)


class Ten(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.t = 0.0
        self.mode = 0

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())
            self.fg = True
        self.t += delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.mode = (self.mode + 1) % 3
        return True

    def _colors(self):
        # one (r,g,b) 0..1 per LED index 0..11, from a single phase
        t = self.t
        out = []
        head = (t * 1.6) % 12
        for i in range(12):
            if self.mode == 0:                        # comet
                d = min((i - head) % 12, (head - i) % 12)
                f = max(0.0, 1.0 - d / 3.5)
                out.append((f, f * 0.6, 0.1 * f + 0.0))
            elif self.mode == 1:                      # pulse
                f = 0.15 + 0.85 * (0.5 + 0.5 * math.sin(t * 3 - i * 0.0))
                out.append((0.1 * f, f, f))
            else:                                     # rainbow
                r, g, bl = _hue(i / 12.0 + t * 0.2)
                out.append((r, g, bl))
        return out, head

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        cols, head = self._colors()
        for i in range(12):
            r, g, bl = cols[i]
            tildagonos.leds[i + 1] = (int(r * 255), int(g * 255), int(bl * 255))
            a = _ang(i)
            x = RING * math.cos(a)
            y = RING * math.sin(a)
            ctx.rgb(max(0.0, min(1.0, r)), max(0.0, min(1.0, g)),
                    max(0.0, min(1.0, bl)))
            ctx.arc(x, y, 9 + 6 * (r + g + bl) / 3.0, 0, TAU, True).fill()
        tildagonos.leds.write()
        # a hand pointing at the comet head so the lock is obvious
        if self.mode != 1:
            a = _ang(head)
            ctx.line_width = 3
            ctx.rgb(0.9, 0.9, 0.9)
            ctx.move_to(0, 0).line_to(RING * 0.7 * math.cos(a),
                                      RING * 0.7 * math.sin(a)).stroke()
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.font_size = 15
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 4).text(("comet", "pulse", "rainbow")[self.mode])
        ctx.restore()


__app_export__ = Ten
