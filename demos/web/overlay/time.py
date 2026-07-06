# Browser replacement for the sim's fakes/time.py: MicroPython tick functions
# on top of a HOST-CONTROLLED virtual clock instead of the wall clock.
#
# All badge timing flows through time.ticks_ms()/ticks_us() (App.run computes
# update() deltas from it), so routing ticks through chost.nowMs() gives the
# playground pause / single-step / speed control over "badge time" for free,
# while asyncio (real time) keeps the update loop itself breathing.
#
# Like upstream, this file is exec'd INTO the stdlib `time` module via
# importlib.reload() with the fakes dir first on sys.path, so the real
# time.time()/sleep() survive alongside these additions. `_time` is the
# untouched stdlib module, pre-seeded in sys.modules by boot.py.

import _time
import chost


def sleep_ms(ms):
    # Blocking sleeps would freeze the browser tab; nothing on the playground's
    # code path calls this (it exists for API compatibility only).
    pass


def ticks_ms():
    return int(chost.nowMs())


def ticks_us():
    return int(chost.nowMs() * 1000)


def ticks_diff(a, b):
    return a - b


def ticks_add(a, b):
    return a + b
