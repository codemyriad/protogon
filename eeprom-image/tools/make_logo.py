#!/usr/bin/env python3
"""Turn the Codemyriad logo SVG into logo.dat (the 1-bit image the badge shows).

    python3 tools/make_logo.py                 # use tools/logo.svg, write ../logo.dat
    python3 tools/make_logo.py --svg other.svg # use a different SVG
    python3 tools/make_logo.py --size 120      # different resolution

It takes only the logo mark on the left of the wordmark, squares it, and
renders it white-on-black at a small resolution, then packs it as per-row white
runs (see the format note in ../app.py). Only needs Pillow -- the few SVG paths
(straight-line chevrons/bars plus one bezier ring) are rasterized directly, so
no native SVG/cairo library is required.

Re-run this to swap in a different image: point --svg at any simple white-on-
transparent (or dark) SVG, or adapt _render() to load a raster image instead.
"""
import argparse
import os
import re
import sys

LOGO_URL = "https://codemyriad.io/logo.svg"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "logo.dat")
LOCAL_SVG = os.path.join(HERE, "logo.svg")   # committed copy, used if present

NUM = re.compile(r'-?\d*\.?\d+(?:[eE][-+]?\d+)?')
TOK = re.compile(r'([MLHVCZmlhvcz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)')


def _flatten(d, steps=32):
    """Flatten one absolute-command SVG path into subpaths of (x, y) points."""
    toks = [(c or n) for c, n in TOK.findall(d)]
    i = 0
    cx = cy = sx = sy = 0.0
    subs = []
    cur = None
    cmd = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        if re.match(r'[A-Za-z]', toks[i]):
            cmd = toks[i]
            i += 1
        if cmd in ('M', 'm'):
            x = num(); y = num()
            cx, cy = x, y; sx, sy = x, y
            cur = [(cx, cy)]; subs.append(cur); cmd = 'L'
        elif cmd == 'L':
            x = num(); y = num(); cx, cy = x, y; cur.append((cx, cy))
        elif cmd == 'H':
            cx = num(); cur.append((cx, cy))
        elif cmd == 'V':
            cy = num(); cur.append((cx, cy))
        elif cmd == 'C':
            x1 = num(); y1 = num(); x2 = num(); y2 = num(); x = num(); y = num()
            p0 = (cx, cy)
            for s in range(1, steps + 1):
                t = s / steps; u = 1 - t
                cur.append((u*u*u*p0[0] + 3*u*u*t*x1 + 3*u*t*t*x2 + t*t*t*x,
                            u*u*u*p0[1] + 3*u*u*t*y1 + 3*u*t*t*y2 + t*t*t*y))
            cx, cy = x, y
        elif cmd in ('Z', 'z'):
            cx, cy = sx, sy
        else:
            i += 1
    return subs


def _render(svg_text, size):
    from PIL import Image, ImageDraw
    paths = re.findall(r'\bd="([^"]+)"', svg_text)
    # the mark is every path whose points all sit left of the wordmark (x<=40)
    ss = 40
    img = Image.new("L", (40 * ss, 28 * ss), 0)
    drw = ImageDraw.Draw(img)
    marks = 0
    for d in paths:
        xs = [float(x) for x in NUM.findall(d)][0::2]
        if xs and max(xs) <= 40:
            marks += 1
            for sub in _flatten(d):
                pts = [(x * ss, y * ss) for x, y in sub]
                if len(pts) >= 3:
                    drw.polygon(pts, fill=255)
    if not marks:
        sys.exit("no logo-mark paths found in the SVG")
    bbox = img.point(lambda p: 255 if p > 40 else 0).getbbox()
    tight = img.crop(bbox)
    w, h = tight.size
    side = max(w, h)
    sq = Image.new("L", (side, side), 0)
    sq.paste(tight, ((side - w) // 2, (side - h) // 2))
    small = sq.resize((size, size), Image.LANCZOS).point(lambda p: 1 if p > 110 else 0)
    return small


def _pack(img):
    """Pack a 1-bit PIL image as: magic 'PLG1', w, h, then per row: count,
    (start, length) pairs for each white run."""
    w, h = img.size
    if w > 255 or h > 255:
        sys.exit("size must be <= 255 (per-row runs use single-byte coords)")
    px = img.load()
    out = bytearray(b"PLG1")
    out += bytes([w, h])
    runs = 0
    for y in range(h):
        row = bytearray()
        n = 0
        x = 0
        while x < w:
            if px[x, y]:
                s = x
                while x < w and px[x, y]:
                    x += 1
                row += bytes([s, x - s])
                n += 1
            else:
                x += 1
        out.append(n)
        out += row
        runs += n
    return bytes(out), runs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--svg", help="local SVG path (default: fetch %s)" % LOGO_URL)
    ap.add_argument("--size", type=int, default=100, help="pixels per side (<=255)")
    ap.add_argument("--out", default=OUT, help="output .dat path")
    ap.add_argument("--preview", help="also write a PNG preview here")
    args = ap.parse_args()

    if args.svg:
        svg_text = open(args.svg).read()
    elif os.path.exists(LOCAL_SVG):
        svg_text = open(LOCAL_SVG).read()
    else:
        import urllib.request
        print("fetching", LOGO_URL)
        svg_text = urllib.request.urlopen(LOGO_URL).read().decode()

    img = _render(svg_text, args.size)
    data, runs = _pack(img)
    with open(args.out, "wb") as f:
        f.write(data)
    print("wrote %s: %d bytes, %dx%d, %d white runs"
          % (args.out, len(data), args.size, args.size, runs))
    if args.preview:
        img.point(lambda p: 255 if p else 0).resize((240, 240)).save(args.preview)
        print("wrote preview", args.preview)


if __name__ == "__main__":
    main()
