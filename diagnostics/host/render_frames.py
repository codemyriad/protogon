#!/usr/bin/env python3
"""Render the MLX90640 frame(s) the badge printed into results.log as PNG(s).

The badge script prints lines like (note the leading spaces; the parser strips
whitespace before matching, so they don't matter):
      FRAME_B64:<base64 of 768 big-endian uint16 raw ADC values>

Usage:
    python3 render_frames.py results.log            # -> frame_000.png ...
    mpremote run ../protogon_thermal_test.py | python3 render_frames.py -

No hard dependencies: uses Pillow for a colour PNG if available, otherwise
falls back to a plain grayscale .pgm (viewable everywhere, no libs).
"""
import sys
import base64
import struct

W, H = 32, 24
SCALE = 16  # upscale factor for a viewable image

# A small blue->red "ironbow-ish" colormap (value 0..255 -> RGB).
def colormap(v):
    # piecewise: black-blue-purple-red-orange-yellow-white
    stops = [
        (0, (0, 0, 0)), (40, (0, 0, 120)), (90, (120, 0, 160)),
        (140, (210, 40, 40)), (190, (255, 140, 0)),
        (230, (255, 230, 60)), (255, (255, 255, 255)),
    ]
    for i in range(len(stops) - 1):
        v0, c0 = stops[i]
        v1, c1 = stops[i + 1]
        if v0 <= v <= v1:
            f = (v - v0) / (v1 - v0) if v1 > v0 else 0
            return tuple(int(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
    return (255, 255, 255)


def parse_frames(text):
    frames = []
    for line in text.splitlines():
        line = line.strip()
        i = line.find("FRAME_B64:")
        if i < 0:
            continue
        b64 = line[i + len("FRAME_B64:"):].strip()
        try:
            raw = base64.b64decode(b64)
            if len(raw) != W * H * 2:
                continue
            words = struct.unpack(">" + "H" * (W * H), raw)
            signed = [w - 65536 if w >= 32768 else w for w in words]
            frames.append(signed)
        except Exception:
            continue
    return frames


def normalize(signed):
    lo, hi = min(signed), max(signed)
    span = (hi - lo) or 1
    return [(p - lo) * 255 // span for p in signed], lo, hi


def save_png_pillow(norm, path):
    from PIL import Image
    img = Image.new("RGB", (W, H))
    img.putdata([colormap(v) for v in norm])
    img = img.resize((W * SCALE, H * SCALE), Image.NEAREST)
    img.save(path)
    return path


def save_pgm(norm, path):
    path = path.rsplit(".", 1)[0] + ".pgm"
    with open(path, "wb") as f:
        f.write(b"P5\n%d %d\n255\n" % (W * SCALE, H * SCALE))
        for row in range(H):
            line = bytes(norm[row * W + col] for col in range(W))
            big = b"".join(bytes([b]) * SCALE for b in line)
            for _ in range(SCALE):
                f.write(big)
    return path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    text = sys.stdin.read() if src == "-" else open(src).read()
    frames = parse_frames(text)
    if not frames:
        print("No FRAME_B64 lines found. Was EMIT_B64_FRAME = True on the badge?")
        return 1
    for n, signed in enumerate(frames):
        norm, lo, hi = normalize(signed)
        out = "frame_%03d.png" % n
        try:
            out = save_png_pillow(norm, out)
        except Exception:
            out = save_pgm(norm, out)
        print("wrote %s  (raw ADC lo=%d hi=%d)" % (out, lo, hi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
