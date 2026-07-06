# Browser replacement for the sim's fakes/_sim.py (upstream @ 517f12c).
#
# Upstream _sim.py owns the pygame window: it composites the badge photo, LED
# glows, button markers and the 240x240 OLED into one surface. In the browser
# all of that chrome lives in the page DOM, so this file keeps only the badge
# OS-facing surface (the same names display.py / sys_buttons.py / leds.py /
# imu.py import) and hands pixels/LEDs/inputs to JS through `chost`:
#
#   screen  : ctx.wasm renders into a wasm-memory framebuffer; chost.blit(ptr)
#             wraps it in ImageData and paints the OffscreenCanvas (RGBA8 out
#             instead of upstream's BGRA8 -- ImageData is RGBA).
#   LEDs    : set_led_rgb buffers, leds_update() -> chost.setLeds(csv string).
#   buttons : chost.buttons() bitmask, bits 0..5 = physical buttons A..F.
#   IMU     : chost.acc(i) fed by the page (pointer tilt / device orientation).

import chost
import ctx

NUM_BUTTONS = 6


class _Buttons:
    """Same .state() contract as upstream ButtonsInput: list of 6 booleans in
    physical order A..F (A=top, clockwise)."""

    def state(self):
        bits = int(chost.buttons())
        return [bool(bits & (1 << i)) for i in range(NUM_BUTTONS)]


class Simulation:
    # Pixel coordinates of each LED on the 733x733 badge image, same order as
    # upstream (0 = internal, 1..12 = top ring as seen by apps, 13+ = under).
    # The page renders the glows; this list exists because leds.py measures it.
    LED_POSITIONS = [
        (370, 370),
        (443, 90), (573, 163), (646, 293), (646, 440), (573, 566), (443, 640),
        (296, 640), (173, 566), (93, 440), (93, 293), (173, 163), (296, 90),
        (533, 93), (680, 366), (533, 626), (200, 626), (60, 366), (200, 93),
    ]

    def __init__(self):
        self.led_state_buf = [(0.0, 0.0, 0.0) for _ in self.LED_POSITIONS]
        self.led_state = [(0.0, 0.0, 0.0) for _ in self.LED_POSITIONS]
        self.buttons = _Buttons()
        self.acc = [0.0, 0.0]

    def process_events(self):
        # IMU values are produced on the page; refresh our mirror each frame.
        self.acc[0] = float(chost.acc(0))
        self.acc[1] = float(chost.acc(1))

    def render_gui_lazy(self):
        pass

    def render_gui_now(self):
        pass

    def set_led_rgb(self, ix, r, g, b):
        if 0 <= ix < len(self.led_state_buf):
            self.led_state_buf[ix] = (r, g, b)

    def leds_update(self):
        if self.led_state != self.led_state_buf:
            self.led_state = list(self.led_state_buf)
            chost.setLeds(
                ",".join(f"{r:.4f} {g:.4f} {b:.4f}" for (r, g, b) in self.led_state)
            )


_sim = Simulation()

SCREENSHOT = False


def path_replace(p):
    return p


class FramebufferManager:
    def __init__(self):
        self._free = []

        # Unlike the device (RGB565) and unlike upstream's pygame path (BGRA8),
        # everything here is RGBA8: it is byte-identical to canvas ImageData.
        for _ in range(1):
            fb, c = ctx._wasm.ctx_new_for_framebuffer(240, 240, 240 * 4, ctx.RGBA8)
            ctx._wasm.ctx_apply_transform(c, 1, 0, 120, 0, 1, 120, 0, 0, 1)
            self._free.append((fb, c))

        self._overlay = ctx._wasm.ctx_new_for_framebuffer(240, 240, 240 * 4, ctx.RGBA8)
        ctx._wasm.ctx_apply_transform(self._overlay[1], 1, 0, 120, 0, 1, 120, 0, 0, 1)

        self._output = ctx._wasm.ctx_new_for_framebuffer(240, 240, 240 * 4, ctx.RGBA8)

    def get(self):
        if len(self._free) == 0:
            return None, None
        fb, c = self._free[0]
        self._free = self._free[1:]
        return fb, c

    def put(self, fb, c):
        self._free.append((fb, c))

    def get_overlay(self):
        return self._overlay

    def get_output(self, fbp):
        return self._output

    def draw(self, fb):
        ctx._wasm.ctx_define_texture(
            self._output[1], "!fb", 240, 240, 240 * 4, ctx.RGBA8, fb, 0
        )
        ctx._wasm.ctx_parse(self._output[1], "compositingMode copy")
        ctx._wasm.ctx_draw_texture(self._output[1], "!fb", 0, 0, 240, 240)

        if overlay_clip[2] and overlay_clip[3]:
            ctx._wasm.ctx_define_texture(
                self._output[1],
                "!overlay",
                240,
                240,
                240 * 4,
                ctx.RGBA8,
                self._overlay[0],
                0,
            )
            ctx._wasm.ctx_parse(self._output[1], "compositingMode sourceOver")
            ctx._wasm.ctx_draw_texture(self._output[1], "!overlay", 0, 0, 240, 240)


fbm = FramebufferManager()
overlay_ctxs = []
overlay_clip = (0, 0, 240, 240)


def set_overlay_clip(x, y, x2, y2):
    global overlay_clip
    overlay_clip = (x, y, x2 - x, y2 - y)


def get_ctx():
    dctx = ctx._wasm.ctx_new_drawlist(240, 240)
    return ctx.Context(dctx)


def get_overlay_ctx():
    dctx = ctx._wasm.ctx_new_drawlist(240, 240)
    overlay_ctxs.append(dctx)
    return ctx.Context(dctx)


def display_update(subctx):
    _sim.process_events()

    if subctx._ctx in overlay_ctxs:
        overlay_ctxs.remove(subctx._ctx)
        fbp, c = fbm.get_overlay()
        ctx._wasm.ctx_render_ctx(subctx._ctx, c)
        ctx._wasm.ctx_destroy(subctx._ctx)
        return

    fbp, c = fbm.get()
    if fbp is None:
        return

    ctx._wasm.ctx_render_ctx(subctx._ctx, c)
    ctx._wasm.ctx_destroy(subctx._ctx)

    fbm.draw(fbp)
    chost.blit(fbm.get_output(fbp)[0])

    fbm.put(fbp, c)


def get_button_state(left):
    # flow3r-era API kept for sys_buttons.py compatibility.
    state = _sim.buttons.state()
    sub = state[:3] if left == 1 else state[3:6] if left == 0 else [False] * 3
    if sub[0]:
        return -1
    if sub[1]:
        return 2
    if sub[2]:
        return +1
    return 0
