# Protogon thermal viewer: live MLX90640 heatmap on the badge screen.
# Lives on the Protogon's ID EEPROM; the badge auto-launches it on insert.
# Docs: github.com/codemyriad/protogon (app/README.md). Shows raw sensor
# counts auto-scaled (hot = bright), not degrees C.

import struct
import app
from machine import I2C
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

MLX = 0x33      # MLX90640 I2C address (Qwiic camera)
STATUS = 0x8000
CTRL1 = 0x800D
RAM = 0x0400    # 768 pixel words = 32x24
CHUNK = 192     # words per I2C read: ~26 ms of bus each (under the badge
                # driver's 50 ms limit), 4 chunks = ~0.2 s per frame read --
                # well inside the 0.5 s the sensor takes per subpage
CELL = 6        # px per sensor pixel: 32x24 -> 192x144 fits the round screen

# 16-level ironbow palette, cold -> hot, packed RGB bytes
_PAL = (b'\x00\x00\x00\x08\x00\x1b\x0f\x006\x17\x00Q3\x03dX\x06r}\n\x81'
        b'\x9f\x11\x83\xb9"\\\xd236\xe8J\x17\xf2r\r\xfc\x9a\x03\xff\xc4-'
        b'\xff\xeel\xff\xff\xff')


class ProtogonThermal(app.App):
    def __init__(self, config=None):
        self.button_states = Buttons(self)
        self.port = config.port if config else None  # None: scan all slots
        self.i2c = None
        self.state = "scan"          # scan -> init -> wait <-> read
        self.msg = "looking for the camera..."
        self.pal = [(_PAL[i] / 255, _PAL[i + 1] / 255, _PAL[i + 2] / 255)
                    for i in range(0, 48, 3)]
        self.raw = bytearray(768 * 2)
        self.levels = None           # bytearray(768) once a frame lands
        # chunk/fails counters; lo/hi display scale; ms clock + next scan time
        self.chunk = self.fails = self.lo = self.hi = 0
        self.ms = self.next_scan = 0
        self.fg = False
        self.dirty = True

    def _reg(self, a):
        return struct.unpack(
            ">H", self.i2c.readfrom_mem(MLX, a, 2, addrsize=16))[0]

    def _wreg(self, a, v):
        self.i2c.writeto_mem(MLX, a, struct.pack(">H", v), addrsize=16)

    def _scan(self):
        for p in ([self.port] if self.port else [1, 2, 3, 4, 5, 6]):
            try:
                bus = I2C(p)
                if MLX in bus.scan():
                    self.i2c = bus
                    return "init"
            except OSError:
                pass
        self.msg = "no camera found -- check\nthe Qwiic cable and\nthe camera"
        return "scan"

    def _step(self):
        # One small step per update() so a frame read never freezes the UI.
        if self.state == "scan":
            if self.ms < self.next_scan:
                return
            self.next_scan = self.ms + 2000  # bus scans are slow; don't spam
            self.state = self._scan()
            if self.state != "scan":
                self.msg = "camera found --\nwaiting for a frame"
            self.dirty = True
        elif self.state == "init":
            # 2 Hz refresh (CTRL1 bits [9:7] = 2): faster would out-run the
            # badge's 133 kHz bus (a frame is ~0.13 s of bus time).
            self._wreg(CTRL1, (self._reg(CTRL1) & ~0x0380) | (0x2 << 7))
            self.state = "wait"
        elif self.state == "wait":
            if self._reg(STATUS) & 0x0008:   # data ready
                self._wreg(STATUS, 0x0030)   # clear it, keep RAM overwrite
                self.chunk = 0
                self.state = "read"
        else:  # "read": one chunk at a time
            off = self.chunk * CHUNK
            mv = memoryview(self.raw)
            self.i2c.readfrom_mem_into(
                MLX, RAM + off, mv[off * 2:(off + CHUNK) * 2], addrsize=16)
            self.chunk += 1
            if self.chunk * CHUNK >= 768:
                self.state = "wait"
                if self._reg(STATUS) & 0x0008:
                    return   # next subpage landed mid-read: torn frame, drop it
                self._frame_done()
                self.dirty = True

    def _frame_done(self):
        sv = [w - 65536 if w >= 32768 else w
              for w in struct.unpack(">768H", self.raw)]
        flo = min(sv)
        fhi = max(sv)
        if self.levels is None:
            self.levels = bytearray(768)
            self.lo, self.hi = flo, fhi
        span = (self.hi - self.lo) or 1
        clo = self.lo
        lv = self.levels
        for i in range(768):
            n = (sv[i] - clo) * 15 // span
            lv[i] = 0 if n < 0 else (15 if n > 15 else n)
        # ease the scale toward this frame (no auto-scale flicker)
        self.lo += (flo - self.lo) >> 2
        self.hi += (fhi - self.hi) >> 2

    def update(self, delta):
        if not self.fg:   # EEPROM-launched apps start backgrounded
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.minimise()
        self.ms += delta
        try:
            self._step()
            self.fails = 0
        except OSError:
            self.fails += 1
            if self.fails > 8:               # camera unplugged? start over
                self.fails = 0
                self.i2c = None
                self.levels = None           # else draw() shows a frozen frame
                self.state = "scan"
                self.msg = "camera lost --\nrescanning..."
                self.dirty = True
        d = self.dirty
        self.dirty = False
        return d    # False skips the redraw between frames

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.text_align = ctx.CENTER
        if self.levels:
            lv = self.levels
            for r in range(24):
                y = r * CELL - 72
                row = r * 32
                c = 0
                while c < 32:   # merge same-color runs: far fewer rectangles
                    n = lv[row + c]
                    c2 = c + 1
                    while c2 < 32 and lv[row + c2] == n:
                        c2 += 1
                    p = self.pal[n]
                    ctx.rgb(p[0], p[1], p[2]).rectangle(
                        c * CELL - 96, y, (c2 - c) * CELL, CELL).fill()
                    c = c2
            ctx.rgb(0.6, 0.6, 0.6)
            ctx.font_size = 13
            ctx.move_to(0, 94).text("raw %d..%d" % (self.lo, self.hi))
        else:
            ctx.rgb(1.0, 0.6, 0.1)
            ctx.font_size = 18
            ctx.move_to(0, -60).text("Protogon Thermal")
            ctx.rgb(0.85, 0.85, 0.85)
            ctx.font_size = 15
            y = -20
            for line in self.msg.split("\n"):
                ctx.move_to(0, y).text(line)
                y += 20
        ctx.restore()


__app_export__ = ProtogonThermal
