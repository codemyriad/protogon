# Protogon logo viewer: draws a 1-bit image (logo.dat) on the badge screen.
#
# Lives on the hexpansion EEPROM; the badge mounts it and auto-launches this
# class on insert. It doubles as an end-to-end EEPROM check: if the picture
# comes up whole and sharp, the EEPROM stored and returned every byte. The
# flashing tool (flash_logo.py) is the deterministic test; this is the
# human-visible confirmation.
#
# logo.dat format (little, self-describing -- see tools/make_logo.py):
#   bytes 0..3  magic "PLG1"
#   byte  4     width  (<=255)
#   byte  5     height (<=255)
#   then, per row: 1 count byte, then <count> (start, length) white-run pairs.

import app
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

TARGET = 200        # aim to fill a ~200 px square on the 240 px round screen


class ProtogonLogo(app.App):
    def __init__(self, config=None):
        self.button_states = Buttons(self)
        self.port = config.port if config else None
        self.spans = None      # [(row, start, length), ...] white runs
        self.w = self.h = 0
        self.scale = 1
        self.error = None
        self.fg = False
        self.drawn = False
        try:
            self._load()
        except Exception as e:
            self.error = repr(e)

    def _path(self):
        if self.port:
            return "/hexpansion_%d/logo.dat" % self.port
        # launched without a slot (e.g. from the menu): find our mount
        import os
        for p in range(1, 7):
            path = "/hexpansion_%d/logo.dat" % p
            try:
                os.stat(path)
                return path
            except OSError:
                pass
        return "logo.dat"      # simulator / current-directory fallback

    def _load(self):
        with open(self._path(), "rb") as f:
            data = f.read()
        if data[:4] != b"PLG1":
            raise ValueError("bad magic")
        self.w = data[4]
        self.h = data[5]
        self.scale = max(1, TARGET // self.w)
        spans = []
        i = 6
        for row in range(self.h):
            n = data[i]
            i += 1
            for _ in range(n):
                spans.append((row, data[i], data[i + 1]))
                i += 2
        self.spans = spans

    def update(self, delta):
        if not self.fg:                       # EEPROM apps start backgrounded
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
            return None                       # request the first draw
        if self.button_states.get(BUTTON_TYPES["CANCEL"]):
            self.button_states.clear()
            self.drawn = False                # redraw if reopened later
            self.minimise()
        return None if not self.drawn else False   # static: skip idle redraws

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        if self.error is not None:
            ctx.text_align = ctx.CENTER
            ctx.rgb(1.0, 0.3, 0.2)
            ctx.font_size = 17
            ctx.move_to(0, -8).text("logo load failed")
            ctx.rgb(0.85, 0.85, 0.85)
            ctx.font_size = 12
            ctx.move_to(0, 16).text(self.error[:40])
        elif self.spans is not None:
            s = self.scale
            ox = -(self.w * s) // 2
            oy = -(self.h * s) // 2
            ctx.rgb(1, 1, 1)
            for (row, start, length) in self.spans:
                ctx.rectangle(ox + start * s, oy + row * s, length * s, s).fill()
        ctx.restore()
        self.drawn = True


__app_export__ = ProtogonLogo
