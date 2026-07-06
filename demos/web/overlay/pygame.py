# Browser stand-in for the `pygame` module.
#
# The upstream sim fakes import pygame in five places, but almost nothing of it
# is load-bearing once _sim.py is replaced by the browser backend:
#   - fakes/time.py     : imports pygame, never uses it
#   - fakes/leds.py     : pygame.event.post(Event(USEREVENT)) as a repaint nudge
#   - fakes/sys_colors.py: pygame.Color hsva conversions
#   - fakes/media.py, bl00mbox.py: pygame.mixer audio (stubbed silent)
# This module implements exactly that surface and nothing more.

import colorsys

SRCALPHA = 0x00010000
QUIT = 0x100
KEYDOWN = 0x300
KEYUP = 0x301
MOUSEMOTION = 0x400
MOUSEBUTTONDOWN = 0x401
MOUSEBUTTONUP = 0x402
USEREVENT = 0x8000

# Full K_* table so a user config.py can reference any letter/digit key.
for _i in range(26):
    globals()["K_" + chr(ord("a") + _i)] = ord("a") + _i
for _i in range(10):
    globals()["K_" + chr(ord("0") + _i)] = ord("0") + _i
K_UP, K_DOWN, K_LEFT, K_RIGHT = 1073741906, 1073741905, 1073741904, 1073741903
K_RETURN, K_ESCAPE, K_SPACE = 13, 27, 32


def init():
    pass


def quit():
    pass


class Color:
    """Just enough of pygame.Color for sys_colors.py: integer/rgb construction,
    the .hsva property (H 0-360, SVA 0-100) and .normalize()."""

    def __init__(self, r=0, g=0, b=0, a=255):
        if isinstance(r, int) and g == 0 and b == 0 and a == 255 and r > 255:
            # packed int form: 0xRRGGBBAA
            self.r = (r >> 24) & 0xFF
            self.g = (r >> 16) & 0xFF
            self.b = (r >> 8) & 0xFF
            self.a = r & 0xFF
        else:
            self.r, self.g, self.b, self.a = int(r), int(g), int(b), int(a)

    @property
    def hsva(self):
        h, s, v = colorsys.rgb_to_hsv(self.r / 255, self.g / 255, self.b / 255)
        return (h * 360, s * 100, v * 100, self.a / 255 * 100)

    @hsva.setter
    def hsva(self, value):
        h, s, v, a = value
        r, g, b = colorsys.hsv_to_rgb((h % 360) / 360, s / 100, v / 100)
        self.r, self.g, self.b = int(r * 255), int(g * 255), int(b * 255)
        self.a = int(a / 100 * 255)

    def normalize(self):
        return (self.r / 255, self.g / 255, self.b / 255, self.a / 255)


class _EventModule:
    class Event:
        def __init__(self, type, attrs=None, **kwargs):
            self.type = type
            for src in (attrs or {}), kwargs:
                for k, v in src.items():
                    setattr(self, k, v)

    @staticmethod
    def get():
        return []

    @staticmethod
    def post(ev):
        pass


event = _EventModule()
Event = _EventModule.Event


class _SilentChannel:
    def play(self, *a, **k):
        pass

    def set_volume(self, *a, **k):
        pass

    def stop(self, *a, **k):
        pass


class _MixerMusic:
    def load(self, *a, **k):
        pass

    def unload(self):
        pass

    def play(self, *a, **k):
        pass

    def pause(self):
        pass

    def unpause(self):
        pass

    def stop(self):
        pass

    def rewind(self):
        pass

    def get_busy(self):
        return False

    def set_volume(self, v):
        pass

    def get_volume(self):
        return 1.0

    def get_pos(self):
        return 0

    def set_pos(self, p):
        pass


class _Mixer:
    music = _MixerMusic()

    @staticmethod
    def init(*a, **k):
        pass

    @staticmethod
    def Sound(*a, **k):
        return _SilentChannel()


mixer = _Mixer()
