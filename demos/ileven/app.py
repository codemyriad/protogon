# ileven (11) -- Pipes grower. A head walks a grid drawing thick orthogonal
# pipe runs with random turns; when it boxes itself in it starts a fresh pipe in
# a new colour elsewhere. CONFIRM clears the board, CANCEL exits.
#
#   sim: python3 demos/sim/run.py ileven --gif
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

GX = 24
CELL = 9
OFF = -(GX - 1) * CELL / 2.0    # centre the grid
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
PIPE_COLS = ((0.2, 0.9, 1.0), (1.0, 0.5, 0.2), (0.5, 1.0, 0.4),
             (1.0, 0.3, 0.7), (0.8, 0.8, 0.3), (0.6, 0.5, 1.0))
STEPS = 2                        # cells advanced per frame


class Ileven(app.App):
    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False
        self._reset()

    def _reset(self):
        self.visited = set()
        self.segs = []           # (x1, y1, x2, y2, colidx)
        self.col = 0
        self._newpipe()

    def _newpipe(self):
        free = [(x, y) for x in range(GX) for y in range(GX)
                if (x, y) not in self.visited]
        if not free:
            self._reset()
            return
        self.head = random.choice(free)
        self.dir = random.choice(DIRS)
        self.visited.add(self.head)
        self.col = (self.col + 1) % len(PIPE_COLS)

    def _cxy(self, cell):
        return (OFF + cell[0] * CELL, OFF + cell[1] * CELL)

    def _step(self):
        x, y = self.head
        opts = []
        for d in DIRS:
            nx, ny = x + d[0], y + d[1]
            if 0 <= nx < GX and 0 <= ny < GX and (nx, ny) not in self.visited:
                opts.append(d)
        if not opts:
            self._newpipe()
            return
        if self.dir in opts and random.random() < 0.7:
            d = self.dir                              # bias to straight runs
        else:
            d = random.choice(opts)
        nx, ny = x + d[0], y + d[1]
        self.segs.append((self._cxy((x, y)) + self._cxy((nx, ny)) + (self.col,)))
        self.visited.add((nx, ny))
        self.head = (nx, ny)
        self.dir = d
        if len(self.visited) > GX * GX * 0.72:
            self._reset()

    def update(self, delta):
        if not self.fg:
            eventbus.emit(RequestForegroundPushEvent(self))
            self.fg = True
        b = self.button_states
        if b.get(BUTTON_TYPES["CANCEL"]):
            b.clear()
            self.minimise()
            return False
        if b.get(BUTTON_TYPES["CONFIRM"]):
            b.clear()
            self._reset()
        for _ in range(STEPS):
            self._step()
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = 5
        # Batch every pipe's segments into ONE path per colour and stroke once
        # (<=6 stroke() calls/frame) instead of a stroke() per segment -- a full
        # board is ~400 segments, and per-stroke path setup is what stalls the
        # badge. The host sim strokes them all instantly and would hide it.
        for ci in range(len(PIPE_COLS)):
            drew = False
            for (x1, y1, x2, y2, c) in self.segs:
                if c == ci:
                    ctx.move_to(x1, y1).line_to(x2, y2)
                    drew = True
            if drew:
                ctx.rgb(*PIPE_COLS[ci])
                ctx.stroke()
        # bright head
        hx, hy = self._cxy(self.head)
        ctx.rgb(1, 1, 1)
        ctx.arc(hx, hy, 4, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Ileven
