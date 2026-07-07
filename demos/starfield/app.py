# starfield (4) -- IMU starfield. Stars fly toward you; tilt the badge to steer the
# drift, and the LED ring lights the way you lean.
#
# HOW IT WORKS
#   A star is just three numbers: x, y and a depth z that runs from 1 (far
#   away) down to 0 (right at your nose). The whole 3D trick is one divide:
#   screen position = x / z. Far stars huddle near the centre; as z shrinks
#   they slide outward, getting bigger and brighter, until they whoosh past
#   and are recycled at the back. Tilting the badge shoves the whole field
#   sideways -- that is how you steer.
#
# PRIOR ART  the classic perspective-starfield demo effect (and the old Windows
#            "Starfield Simulation" screensaver) -- https://en.wikipedia.org/wiki/Demo_effect
#
# BUTTONS   tilt steers (W/A/S/D in the sim) - UP/DOWN warp speed - CANCEL exits
#
#   sim:   python3 demos/sim/run.py starfield --gif
#   badge: drop demos/starfield into the official simulator's sim/apps/ (see README)
import app
import math
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

# ------------------------------ tweak me -------------------------------------
# In the playground every number is draggable -- grab one and watch the badge.
STARS     = 70              # how many stars ...... try 150 (a blizzard) or 20 (calm)
FOV       = 90.0            # camera zoom ......... 40.0 snow globe, 160.0 warp tunnel
TILT_GAIN = 0.6             # how hard a lean shoves the field .... try 2.0 (twitchy)
SMOOTH    = 0.15            # steering follow-speed. 0.02 oil tanker, 0.5 instant
GROW      = 3.0             # how fat a star gets as it flies past ....... try 8.0
BLUE_TINT = 0.15            # icy blue on bright stars. 0.0 pure white, 0.6 deep space
WARP      = 0.65            # starting warp speed .. 2.0 = hyperspace
STAR      = (1.0, 1.0, 1.0) # star tint (r,g,b) .. try (1.0, 0.9, 0.7) for warm


def read_tilt():
    # The accelerometer says which way gravity pulls, in m/s^2. Reads can
    # hiccup on real hardware and parts are missing in the sim, so fall back
    # to "held flat". A lean of 6 m/s^2 counts as a full-strength push.
    try:
        import imu
        ax, ay, _ = imu.acc_read()
    except (AttributeError, OSError, Exception):
        ax, ay = 0.0, 0.0
    return (max(-1.0, min(1.0, ax / 6.0)),
            max(-1.0, min(1.0, ay / 6.0)))


class Starfield(app.App):
    """Fly a field of [x, y, depth] stars; tilt drifts them sideways."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.warp = WARP       # fly speed -- UP/DOWN change it while running
        self.tiltx = 0.0       # smoothed lean, -1..1
        self.tilty = 0.0
        # scatter the stars, each already partway along its journey
        self.stars = [[random.uniform(-1, 1), random.uniform(-1, 1),
                       random.uniform(0.05, 1.0)] for _ in range(STARS)]

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())   # we drive the LED ring ourselves
            self.fg = True
        dt = delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())    # hand the ring back
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["UP"]):
            b.clear()
            self.warp = min(2.0, self.warp * 1.4)
        if b.get(BUTTON_TYPES["DOWN"]):
            b.clear()
            self.warp = max(0.15, self.warp / 1.4)
        self.steer()
        self.fly(dt)
        self.light_leds()
        return True

    def steer(self):
        # ease the steering toward the tilt reading instead of jumping to it,
        # so it feels like banking a spaceship, not flicking a switch
        tx, ty = read_tilt()
        self.tiltx += (tx - self.tiltx) * SMOOTH
        self.tilty += (ty - self.tilty) * SMOOTH

    def fly(self, dt):
        for star in self.stars:
            star[2] -= self.warp * dt               # rush toward the camera
            star[0] += self.tiltx * dt * TILT_GAIN  # the lean drags the field
            star[1] += self.tilty * dt * TILT_GAIN
            # flew past us, or drifted far off to the side? recycle it
            if star[2] <= 0.05 or abs(star[0]) > 2 or abs(star[1]) > 2:
                star[0] = random.uniform(-1, 1)
                star[1] = random.uniform(-1, 1)
                star[2] = 1.0                       # back to the far plane

    def light_leds(self):
        # point the ring where you are leaning: one bright LED at the lean
        # angle with a dim one either side
        for i in range(1, 13):
            tildagonos.leds[i] = (0, 0, 0)
        lean = (self.tiltx ** 2 + self.tilty ** 2) ** 0.5
        if lean > 0.08:                             # ignore tiny wobbles
            angle = math.atan2(self.tilty, self.tiltx)
            idx = int(round((angle + math.pi / 2) / 6.28318 * 12)) % 12
            glow = int(min(1.0, lean) * 255)
            dim = glow // 3
            tildagonos.leds[idx + 1] = (glow, glow, glow)
            tildagonos.leds[(idx + 1) % 12 + 1] = (dim, dim, dim)
            tildagonos.leds[(idx + 11) % 12 + 1] = (dim, dim, dim)
        tildagonos.leds.write()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        for star in self.stars:
            z = star[2]
            px = star[0] / z * FOV      # the one-divide perspective trick
            py = star[1] / z * FOV
            if px * px + py * py > 118.0 * 118.0:   # off the round glass
                continue
            bright = 1.0 - z            # nearer = brighter
            if bright < 0.05:           # newborn stars are too dim to see
                continue
            ctx.rgba(bright * STAR[0], bright * STAR[1],
                     min(1.0, bright + BLUE_TINT) * STAR[2], 1.0)
            ctx.arc(px, py, 0.5 + bright * GROW, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Starfield

# ------------------------------ try this --------------------------------------
# - drag FOV down to 40.0: the field huddles into a snow globe; now push it
#   past 150.0 and you are staring down a warp tunnel
# - set SMOOTH to 0.02 and tilt: the steering keeps gliding long after you
#   level out, like a ship slow to answer the helm
# - in fly(), change  self.warp * dt  to  self.warp * dt * (2.0 - star[2]):
#   stars now accelerate as they get close, a proper hyperspace jump
