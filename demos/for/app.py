# for (4) -- IMU starfield. Stars fly toward you; tilt the badge to steer the
# drift (the accelerometer biases the field). One LED lights in the lean
# direction. CANCEL exits. In the sim, W/A/S/D tilt; this host-sim auto-orbits.
#
#   sim: python3 demos/sim/run.py for --gif
import app
import math
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent
from system.patterndisplay.events import PatternDisable, PatternEnable
from tildagonos import tildagonos

NSTARS = 70
FOV = 90.0
MAXR = 118.0


def safe_acc():
    # accelerometer is (x, y, z) m/s^2 on the badge, dummy in the sim; guard the
    # sim-only gaps and any real-hardware I2C hiccup, then fall back to "flat".
    try:
        import imu
        return imu.acc_read()
    except (AttributeError, OSError, Exception):
        return (0.0, 0.0, 9.80665)


class For(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self.warp = 0.65
        self.tiltx = 0.0
        self.tilty = 0.0
        import random
        self.stars = []
        for _ in range(NSTARS):
            self.stars.append([random.uniform(-1, 1), random.uniform(-1, 1),
                               random.uniform(0.05, 1.0)])

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            eventbus.emit(PatternDisable())
            self.fg = True
        dt = delta / 1000.0
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            eventbus.emit(PatternEnable())
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["UP"]):
            b.clear()
            self.warp = min(2.0, self.warp * 1.4)
        if b.get(BUTTON_TYPES["DOWN"]):
            b.clear()
            self.warp = max(0.15, self.warp / 1.4)
        ax, ay, _ = safe_acc()
        # normalise m/s^2 to roughly -1..1 and low-pass for smooth steering
        tx = max(-1.0, min(1.0, ax / 6.0))
        ty = max(-1.0, min(1.0, ay / 6.0))
        self.tiltx += (tx - self.tiltx) * 0.15
        self.tilty += (ty - self.tilty) * 0.15
        import random
        for s in self.stars:
            s[2] -= self.warp * dt
            s[0] += self.tiltx * dt * 0.6
            s[1] += self.tilty * dt * 0.6
            if s[2] <= 0.05 or s[0] < -2 or s[0] > 2 or s[1] < -2 or s[1] > 2:
                s[0] = random.uniform(-1, 1)
                s[1] = random.uniform(-1, 1)
                s[2] = 1.0
        self._leds()
        return True

    def _leds(self):
        mag = (self.tiltx ** 2 + self.tilty ** 2) ** 0.5
        for i in range(1, 13):
            tildagonos.leds[i] = (0, 0, 0)
        if mag > 0.08:
            ang = math.atan2(self.tilty, self.tiltx)
            idx = int(round((ang + math.pi / 2) / (6.28318) * 12)) % 12
            b = int(min(1.0, mag) * 255)
            tildagonos.leds[idx + 1] = (b, b, b)
            tildagonos.leds[(idx + 1) % 12 + 1] = (b // 3, b // 3, b // 3)
            tildagonos.leds[(idx + 11) % 12 + 1] = (b // 3, b // 3, b // 3)
        tildagonos.leds.write()

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        for s in self.stars:
            z = s[2]
            sx = s[0] / z * FOV
            sy = s[1] / z * FOV
            if sx * sx + sy * sy > MAXR * MAXR:
                continue
            b = 1.0 - z
            if b < 0.05:
                continue
            r = 0.5 + (1.0 - z) * 3.0
            ctx.rgba(b, b, min(1.0, b + 0.15), 1.0)
            ctx.arc(sx, sy, r, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = For
