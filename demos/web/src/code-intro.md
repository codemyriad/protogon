# Make art with code — fourteen tiny programs

A small program can be a piece of art, and changing one is the fastest way
to learn that. This file is fourteen complete programs, each about a hundred
lines of Python, each drawing something alive: a dot field driven by one
formula, interference rings, a strange attractor, digital rain, glowing
metaballs. Nothing here needs a framework, a build step, or an account —
each program is one file with one idea in it.

They run on the [EMF Tildagon](https://tildagon.badge.emfcamp.org/) badge,
and — this is the fun part — in your browser, next to their own source code,
**live**: <https://silvio-demos.pgs.sh>

**The point is to change them.** In the playground every plain number in the
code is draggable, colours get a click-to-pick swatch, and edits take effect
as you type — no run button, no reload. If an edit breaks, the badge keeps
running the last working version while the error points at your line, so
there is nothing to be afraid of. Each program tells you where to start:

- a `HOW IT WORKS` header that explains the one idea in plain words,
- a `tweak me` block of knobs with suggested values to try,
- a `try this` footer of small experiments that actually work.

None of these ideas are new, and that's the other lesson: the header of each
program links its prior art — arcade games, demoscene effects, screensavers,
a Scientific American column from 1986. People have been making art with
tiny programs for half a century. These are yours to continue: take one,
drag its numbers until it feels like yours, rename it, show someone.

*From the [protogon](https://github.com/codemyriad/protogon) project
(`badge-demos` branch), which also carries the host simulator and the
browser playground these run in. The playground runs the unmodified badge
firmware — scheduler, event bus and ctx renderer — under Python-in-WebAssembly,
so what you see in the browser is what the badge does.*
