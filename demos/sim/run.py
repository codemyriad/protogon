#!/usr/bin/env python3
"""Run a Tildagon badge demo on this PC and render it to frames + a GIF.

    python3 demos/sim/run.py --list                 # show the demo names
    python3 demos/sim/run.py tixy --gif              # render demo "tixy" to a GIF
    python3 demos/sim/run.py starfield --gif --frames 60  # longer capture
    python3 demos/sim/run.py all --gif              # render every demo

Each demo lives in demos/<name>/app.py and is an unmodified badge app
(update/draw/__app_export__). This harness fakes the badge runtime (see
tildagon_sim.py), drives update()/draw(), scripts a few button presses and a
moving IMU so interactivity is visible, writes PPM frames and -- if ffmpeg is
present and --gif is given -- stitches them into demos/<name>/<name>.gif.

Logic + composition only: real colours, timing and the on-glass round crop
still need the badge or the official SDL2 simulator (see demos/README.md).
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEMOS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import tildagon_sim as sim  # noqa: E402


# Per-demo input timelines: {name: [(update_index, "BUTTON"), ...]}. The press
# is injected for exactly one update() (a tap) so the GIF shows the demo react.
SCRIPTS = {
    "tixy":   [(30, "RIGHT"), (60, "RIGHT"), (90, "RIGHT"), (120, "UP"), (150, "DOWN")],
    "moire":   [(40, "RIGHT"), (80, "RIGHT")],
    "qix":   [(50, "CONFIRM"), (100, "RIGHT")],
    "kaleidoscope":  [(40, "CONFIRM"), (80, "RIGHT"), (120, "LEFT")],
    "hopalong": [(60, "RIGHT"), (120, "RIGHT")],
    "matrixrain":   [(70, "RIGHT")],
    "plasma":  [(50, "RIGHT"), (100, "RIGHT")],
    "ledring":   [(60, "RIGHT")],
    "pipes": [(80, "CONFIRM")],
    "cellular": [(40, "CONFIRM"), (90, "RIGHT")],
    "ribbons": [(60, "RIGHT")],
    "metaballs": [(50, "RIGHT")],
}


def list_demos():
    out = []
    for name in sorted(os.listdir(DEMOS)):
        if name == "sim":
            continue
        if os.path.isfile(os.path.join(DEMOS, name, "app.py")):
            out.append(name)
    return out


def parse_press(spec):
    events = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        idx, btn = part.split(":")
        events.append((int(idx), btn.strip().upper()))
    return events


def render(name, frames, warmup, every, step_ms, outdir, make_gif, fps,
           round_mask, num_leds, press):
    app_path = os.path.join(DEMOS, name, "app.py")
    if not os.path.isfile(app_path):
        print("no such demo: %s (try --list)" % name)
        return False

    # a clean module table per demo, so one demo's fakes never leak into another
    for m in list(sys.modules):
        if m in ("app", "events", "events.input", "system", "system.eventbus",
                 "system.scheduler", "system.scheduler.events", "tildagonos",
                 "imu", "app_components", "app_components.tokens",
                 "system.patterndisplay", "system.patterndisplay.events"):
            del sys.modules[m]
    sim.Buttons.pressed = set()
    handle = sim.install_fakes(num_leds=num_leds)
    app = sim.load_app(app_path, port=None)

    schedule = {}
    for idx, btn in (press if press is not None else SCRIPTS.get(name, [])):
        schedule.setdefault(idx, []).append(btn)

    os.makedirs(outdir, exist_ok=True)
    ctx = sim.Ctx()
    total = warmup + frames * every
    captured = 0
    paths = []
    for i in range(total):
        sim.Buttons.pressed = set(schedule.get(i, []))
        handle.imu.t += step_ms / 1000.0
        redraw = app.update(step_ms)           # state advances every step
        capture = i >= warmup and (i - warmup) % every == 0 and captured < frames
        if capture and redraw is not False:    # only rasterise frames we keep
            app.draw(ctx)                      # each demo fully redraws from state
            w, h, buf = sim.compose(ctx, handle.tildagonos.leds, round_mask)
            p = os.path.join(outdir, "frame_%03d.ppm" % captured)
            sim.save_ppm(p, w, h, buf)
            paths.append(p)
            captured += 1

    fg = [e for e in handle.eventbus.emitted
          if isinstance(e, sim.RequestForegroundPushEvent)]
    note = "%d frames" % captured
    if len(fg) != 1:
        note += "  [!] expected 1 foreground request, saw %d" % len(fg)
    else:
        note += "  (foregrounded once)"
    print("  %-9s %s -> %s" % (name, note, outdir))

    if make_gif and paths:
        gif = os.path.join(DEMOS, name, "%s.gif" % name)
        if _make_gif(outdir, fps, gif):
            print("             gif -> %s" % gif)
        else:
            print("             (ffmpeg missing or failed; PPM frames kept)")
    return True


def _make_gif(outdir, fps, gif):
    filt = "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer"
    cmd = ["ffmpeg", "-y", "-framerate", str(fps),
           "-i", os.path.join(outdir, "frame_%03d.ppm"),
           "-vf", filt, "-loop", "0", gif]
    try:
        r = subprocess.run(cmd, capture_output=True)
        return r.returncode == 0 and os.path.isfile(gif)
    except FileNotFoundError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Render Tildagon badge demos to GIFs.")
    ap.add_argument("name", nargs="?", help="demo name, or 'all'")
    ap.add_argument("--list", action="store_true", help="list demo names and exit")
    ap.add_argument("--frames", type=int, default=48, help="frames to capture")
    ap.add_argument("--warmup", type=int, default=8, help="updates before capture")
    ap.add_argument("--every", type=int, default=2, help="updates between captures")
    ap.add_argument("--step-ms", type=int, default=40, help="delta per update() (ms)")
    ap.add_argument("--fps", type=int, default=16, help="GIF frame rate")
    ap.add_argument("--gif", action="store_true", help="assemble a GIF via ffmpeg")
    ap.add_argument("--no-round", action="store_true", help="do not apply the round-screen mask")
    ap.add_argument("--leds", type=int, default=sim.NUM_LEDS, help="LED ring size")
    ap.add_argument("--press", help='override input, e.g. "30:RIGHT,60:CONFIRM"')
    ap.add_argument("--out", help="frame output dir (default: scratch under the demo)")
    args = ap.parse_args()

    if args.list or not args.name:
        print("demos:", " ".join(list_demos()))
        return

    press = parse_press(args.press) if args.press else None
    names = list_demos() if args.name == "all" else [args.name]
    print("### TILDAGON DEMO SIM -- logic + composition only, not badge timing/colour ###")
    for name in names:
        outdir = args.out or os.path.join(DEMOS, name, "_frames")
        render(name, args.frames, args.warmup, args.every, args.step_ms, outdir,
               args.gif, args.fps, not args.no_round, args.leds, press)
    print("### END ###")


if __name__ == "__main__":
    main()
