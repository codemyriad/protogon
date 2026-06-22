#!/usr/bin/env python3
"""Convert the Code Myriad emblem (left part of the official logo.svg) into the
silkscreen polygon set used by generate_protogon.py.

Source : https://codemyriad.io/logo.svg  (full horizontal lockup: emblem + wordmark)
Keeps  : only the emblem (SVG x < 40; the 'codemyriad' wordmark is to the right)
Output : tools/codemyriad-logo.json  -- polygons in mm, centered on their own origin
         (consumed by generate_protogon.py: add_logo()). Optionally a preview PNG.

Usage:
  python3 tools/svg_logo_to_silk.py [path-or-url-to-logo.svg] [--preview out.png]

The emblem is left/right and top/bottom symmetric and the ring's hole is preserved
by a bridge already present in the source path, so each SVG fill path maps to one
filled silk polygon -- no hole/mirror handling needed downstream.
"""
import json, re, sys, urllib.request
from pathlib import Path

TARGET_W_MM = 10.0
EMBLEM_MAX_X = 40.0   # SVG units; wordmark starts to the right of this
HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "codemyriad-logo.json"

TOKEN = re.compile(r"([MmLlHhVvCcZz])|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def bezier(p0, p1, p2, p3, n=20):
    out = []
    for i in range(1, n + 1):
        t = i / n; mt = 1 - t
        out.append((mt**3*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t**3*p3[0],
                    mt**3*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t**3*p3[1]))
    return out


def parse_path(d):
    stream = []
    for cmd, num in TOKEN.findall(d):
        stream.append(("cmd", cmd) if cmd else ("num", float(num)))
    i = 0; subpaths = []; cur = []; x = y = 0.0; start = (0.0, 0.0); cmd = None

    def take(k):
        nonlocal i
        vals = [stream[i + j][1] for j in range(k)]; i += k; return vals

    while i < len(stream):
        t, v = stream[i]
        if t == "cmd":
            cmd = v; i += 1
            if cmd in "Zz":
                if cur: cur.append(cur[0]); subpaths.append(cur); cur = []
                x, y = start
            continue
        rel = cmd.islower(); C = cmd.upper()
        if C == "M":
            nx, ny = take(2); x, y = (x+nx, y+ny) if rel else (nx, ny)
            if cur: subpaths.append(cur)
            cur = [(x, y)]; start = (x, y); cmd = "l" if rel else "L"
        elif C == "L":
            nx, ny = take(2); x, y = (x+nx, y+ny) if rel else (nx, ny); cur.append((x, y))
        elif C == "H":
            nx, = take(1); x = x+nx if rel else nx; cur.append((x, y))
        elif C == "V":
            ny, = take(1); y = y+ny if rel else ny; cur.append((x, y))
        elif C == "C":
            x1, y1, x2, y2, nx, ny = take(6)
            if rel: x1, y1, x2, y2, nx, ny = x+x1, y+y1, x+x2, y+y2, x+nx, y+ny
            cur += bezier((x, y), (x1, y1), (x2, y2), (nx, ny)); x, y = nx, ny
        else:
            i += 1
    if cur: subpaths.append(cur)
    return subpaths


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = args[0] if args else "https://codemyriad.io/logo.svg"
    svg = (urllib.request.urlopen(src).read().decode() if src.startswith("http")
           else Path(src).read_text())

    polys = []
    for d in re.findall(r'<path[^>]*\bd="([^"]+)"', svg):
        for sp in parse_path(d):
            if len(sp) >= 3 and max(p[0] for p in sp) < EMBLEM_MAX_X:
                polys.append(sp)
    if not polys:
        sys.exit("no emblem polygons found")

    xs = [p[0] for sp in polys for p in sp]; ys = [p[1] for sp in polys for p in sp]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w, h = maxx - minx, maxy - miny
    scale = TARGET_W_MM / w; cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    mm_polys = [[((px - cx) * scale, (py - cy) * scale) for px, py in sp] for sp in polys]
    OUT_JSON.write_text(json.dumps(
        {"source": src, "target_w_mm": TARGET_W_MM, "size_mm": [TARGET_W_MM, h * scale],
         "polys": mm_polys}))
    print(f"{len(polys)} polys, {TARGET_W_MM}x{h*scale:.2f} mm -> {OUT_JSON}")

    if "--preview" in sys.argv:
        from PIL import Image, ImageDraw
        out = sys.argv[sys.argv.index("--preview") + 1]
        PW = 800; PH = int(PW * h / w)
        img = Image.new("L", (PW, PH), 0); dr = ImageDraw.Draw(img)
        for sp in polys:
            dr.polygon([((px-minx)/w*PW, (py-miny)/h*PH) for px, py in sp], fill=255)
        img.save(out); print("preview ->", out)


if __name__ == "__main__":
    main()
