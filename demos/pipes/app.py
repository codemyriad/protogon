# pipes (11) -- Pipes grower. A head walks a hidden grid laying colourful
# pipes with random turns, like the classic screensaver. CONFIRM clears.
#
# HOW IT WORKS
#   The screen hides a grid of little cells. Each step, the pipe's head asks
#   "which neighbour cells are still empty?" and moves into one -- preferring
#   to keep going straight, which is what makes those long satisfying runs.
#   Boxed in with nowhere left to go? A new pipe starts somewhere empty, in
#   the next colour. Once most of the board is pipe, everything wipes clean
#   and the plumbing begins again.
#
# PRIOR ART  the Windows NT "3D Pipes" screensaver --
#            https://devblogs.microsoft.com/oldnewthing/20240611-00/?p=109881
#
# BUTTONS   CONFIRM clears the board - CANCEL exits
#
#   sim:   python3 demos/sim/run.py pipes --gif
#   badge: drop demos/pipes into the official simulator's sim/apps/ (see README)
import app
import random
from events.input import Buttons, BUTTON_TYPES
from system.eventbus import eventbus
from system.scheduler.events import RequestForegroundPushEvent

# ------------------------------ tweak me -------------------------------------
# Drag a number to change it (double-tap for a slider on a touchscreen);
# the "MIN<n<MAX" notes set each slider's range.
GRID     = 24     # 4<n<40  cells per side .......... try 12 (with CELL 18: fat pipes)
CELL     = 9      # 4<n<40  px between cell centres .. the grid step; try 18
SPEED    = 2      # 0<n<12  cells grown per frame .... try 6 for time-lapse plumbing
STRAIGHT = 0.7    # 0<n<1   chance to keep straight .. 0.95 long runs, 0.0 scribble
FULL     = 0.72   # 0<n<1   board fraction that triggers a wipe ....... try 0.98
PIPE_W   = 5      # 0<n<20  pipe thickness in px ..... try 11 (pairs well with CELL 18)
HEAD_R   = 4      # 0<n<12  radius of the glowing white head
PIPE_COLS = ((0.2, 0.9, 1.0), (1.0, 0.5, 0.2), (0.5, 1.0, 0.4),
             (1.0, 0.3, 0.7), (0.8, 0.8, 0.3), (0.6, 0.5, 1.0))

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))    # right, left, down, up


def cell_centre(cell):
    # grid coordinates -> screen pixels, with the whole grid centred
    off = -(GRID - 1) * CELL / 2.0
    return (off + cell[0] * CELL, off + cell[1] * CELL)


class Pipes(app.App):
    """Grow pipes cell by cell; draw the finished runs and the bright head."""

    def __init__(self, config=None):
        super().__init__()
        self.button_states = Buttons(self)
        self.fg = False        # have we taken the screen yet?
        self.wipe_board()

    def wipe_board(self):
        self.visited = set()   # cells already claimed by a pipe
        self.segs = []         # finished pipe pieces: (x1, y1, x2, y2, colour)
        self.col = 0           # which palette entry the current pipe wears
        self.start_pipe()

    def start_pipe(self):
        # begin a fresh pipe on any still-empty cell, in the next colour
        free = [(x, y) for x in range(GRID) for y in range(GRID)
                if (x, y) not in self.visited]
        if not free:
            self.wipe_board()
            return
        self.head = random.choice(free)
        self.dir = random.choice(DIRS)
        self.visited.add(self.head)
        self.col = (self.col + 1) % len(PIPE_COLS)

    def grow(self):
        # one step: pick an empty neighbour (favouring straight ahead), move in
        x, y = self.head
        opts = []
        for d in DIRS:
            nx, ny = x + d[0], y + d[1]
            if 0 <= nx < GRID and 0 <= ny < GRID and (nx, ny) not in self.visited:
                opts.append(d)
        if not opts:
            self.start_pipe()          # boxed in -- abandon it, start afresh
            return
        if self.dir in opts and random.random() < STRAIGHT:
            d = self.dir
        else:
            d = random.choice(opts)    # turn a corner
        nx, ny = x + d[0], y + d[1]
        self.segs.append(cell_centre((x, y)) + cell_centre((nx, ny)) + (self.col,))
        self.visited.add((nx, ny))
        self.head = (nx, ny)
        self.dir = d
        if len(self.visited) > GRID * GRID * FULL:
            self.wipe_board()          # board is crowded -- start over

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
            self.wipe_board()
        for _ in range(SPEED):
            self.grow()
        return True

    def draw(self, ctx):
        ctx.save()
        ctx.rgb(0, 0, 0).rectangle(-120, -120, 240, 240).fill()
        ctx.line_width = PIPE_W
        # Batch all segments of one colour into a single path and stroke once
        # (<=6 stroke() calls per frame). A full board is ~400 segments, and a
        # stroke() per segment is what stalls the real badge.
        for ci in range(len(PIPE_COLS)):
            drew = False
            for (x1, y1, x2, y2, c) in self.segs:
                if c == ci:
                    ctx.move_to(x1, y1).line_to(x2, y2)
                    drew = True
            if drew:
                ctx.rgb(*PIPE_COLS[ci])
                ctx.stroke()
        # the head: a bright white bead so you can watch it think
        hx, hy = cell_centre(self.head)
        ctx.rgb(1, 1, 1)
        ctx.arc(hx, hy, HEAD_R, 0, 6.2832, True).fill()
        ctx.restore()


__app_export__ = Pipes

# ------------------------------ try this --------------------------------------
# - drag / double-tap STRAIGHT to 0.0: the head coin-flips at every cell and scribbles;
#   at 0.95 it shoots long straight runs and only turns when it must
# - GRID = 12, CELL = 18, PIPE_W = 11: chunky retro plumbing, same footprint
# - FULL = 0.98: watch pipes squeeze into the last free corners before the wipe
