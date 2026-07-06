# Browser copy of the sim's fakes/display.py (upstream @ 517f12c) with one
# change: the fps window is bounded. Upstream prunes `times` by timestamp
# only, which never removes anything while the playground's virtual clock is
# paused (time.ticks_ms() is frozen but frames keep rendering) — the list
# would grow ~20 entries/second forever.
import _sim
import time


def gfx_init():
    pass


times = []


def end_frame(ctx):
    global times
    now = time.ticks_ms()
    times.append(now)
    times = [t for t in times if t > now - 1000][-64:]
    _sim.display_update(ctx)


def get_ctx():
    return _sim.get_ctx()


def hexagon(ctx, x, y, dim):
    return ctx.round_rectangle(x - dim, y - dim, 2 * dim, 2 * dim, dim).fill()


def get_fps():
    return len(times)
