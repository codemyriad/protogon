# ten (10) -- LED / display phase-lock. Twelve dots on the glass sit at the
# same angles as the 12 bezel LEDs; one shared phase animates both in lockstep.
#
# HOW IT WORKS
#   The badge has 12 LEDs around its rim. Each frame we keep ONE clock (the
#   phase), turn it into 12 colours, and send every colour to two places at
#   once: the real LED, and a dot drawn on screen at that LED's exact angle.
#   Same numbers in, same light out -- glass and bezel can never drift apart.
#   (A system service owns the LEDs; we borrow the ring and return it on exit.)
#
# BUTTONS   LEFT/RIGHT cycle comet -> pulse -> rainbow - CANCEL exits
#
#   sim:   python3 demos/sim/run.py ten --gif
#   badge: drop demos/ten into the official simulator's sim/apps/ (see README)
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

TAU = 6.28318

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
SPEED = 1.6                 # comet speed, LEDs per second .... race it: 5.0
TAIL = 3.5                  # LEDs the tail fades over . try 1.5 (spark) or 6.0
RING = 88                   # radius of the on-screen ring .... pull it in: 60
DOT_MIN = 9                 # dot size when its LED is dark ... try 4
DOT_GROW = 6                # extra size at full brightness ... try 14 (blobby)
PULSE_RATE = 3.0            # heartbeats, roughly per second .. calm it: 1.0
SPIN = 0.2                  # rainbow turns per second .. try -0.2 to reverse
COMET = (1.0, 0.6, 0.1)     # comet colour (amber) .. icy: (0.2, 0.6, 1.0)


def hue(h):
    # walk 0..1 around the colour wheel: red -> yellow -> green -> blue -> red
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


def led_angle(i):
    # LED 1 sits at the top of the badge; each next one is 1/12 turn clockwise
    return -math.pi / 2 + i * (TAU / 12)


class Ten(app.App):
    """One phase, twelve colours, two outputs: the LEDs and the screen."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen + LEDs yet?
        self.t = 0.0           # the shared phase: seconds since start
        self.mode = 0          # 0 comet, 1 pulse, 2 rainbow

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())   # our ring now
            self.fg = True
        self.t += delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())    # give the ring back
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["RIGHT"]) or b.get(BUTTON_TYPES["LEFT"]):
            b.clear()
            self.mode = (self.mode + 1) % 3
        return True

    def ring_colours(self):
        # turn the one phase into 12 (r,g,b) 0..1 colours + where the head is
        t = self.t
        head = (t * SPEED) % 12               # comet position, in LED numbers
        out = []
        for i in range(12):
            if self.mode == 0:                        # comet
                d = min((i - head) % 12, (head - i) % 12)   # ring distance
                f = max(0.0, 1.0 - d / TAIL)  # 1 at the head, 0 far behind
                out.append((f * COMET[0], f * COMET[1], f * COMET[2]))
            elif self.mode == 1:                      # pulse
                # every LED breathes together (drag the 0.0 to twist it)
                wave = math.sin(t * PULSE_RATE - i * 0.0)
                f = 0.15 + 0.85 * (0.5 + 0.5 * wave)
                out.append((0.1 * f, f, f))
            else:                                     # rainbow
                out.append(hue(i / 12.0 + t * SPIN))  # each LED 1/12 further
        return out, head

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        cols, head = self.ring_colours()
        for i in range(12):
            r, g, bl = cols[i]
            # the SAME colour goes to the physical LED and to the screen dot
            tildagonos.leds[i + 1] = (int(r * 255), int(g * 255), int(bl * 255))
            a = led_angle(i)
            x = RING * math.cos(a)
            y = RING * math.sin(a)
            ctx.rgb(max(0.0, min(1.0, r)), max(0.0, min(1.0, g)),
                    max(0.0, min(1.0, bl)))
            bright = (r + g + bl) / 3.0       # brighter LED = bigger dot
            ctx.arc(x, y, DOT_MIN + DOT_GROW * bright, 0, TAU, True).fill()
        tildagonos.leds.write()
        if self.mode != 1:
            # a hand pointing at the comet head, so the lockstep is obvious
            a = led_angle(head)
            ctx.line_width = 3
            ctx.rgb(0.9, 0.9, 0.9)
            ctx.move_to(0, 0).line_to(RING * 0.7 * math.cos(a),
                                      RING * 0.7 * math.sin(a)).stroke()
        ctx.rgb(0.6, 0.6, 0.6)
        ctx.font_size = 15
        ctx.text_align = ctx.CENTER
        ctx.move_to(0, 4).text(("comet", "pulse", "rainbow")[self.mode % 3])
        ctx.restore()


__app_export__ = Ten

# ------------------------------ try this --------------------------------------
# - in pulse mode, drag the 0.0 in "i * 0.0" up to 0.5: the shared heartbeat
#   unrolls into a wave chasing itself around the ring
# - set TAIL to 12.0: the whole ring glows and the comet becomes a soft tide
# - make SPEED negative (-1.6): comet, pointer and LEDs all reverse together --
#   every one of them reads the same phase
