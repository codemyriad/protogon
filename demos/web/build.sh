#!/usr/bin/env bash
# Build the Tildagon live playground into ./dist — a fully static site.
#
# Downloads (cached in .cache/, all version-pinned):
#   - pyodide 314.0.2           the 5 files needed to self-host CPython-in-wasm
#   - badge-2024-software       official firmware + sim @ BADGE_SHA (MIT)
# Everything is served same-origin; the built site has zero runtime
# dependencies on any CDN.
#
# Usage:  ./build.sh          (needs: bash, curl, tar, python3, node >= 20)

set -euo pipefail

PYODIDE_VERSION=314.0.2
BADGE_SHA=517f12c478ddef7bd86f277bd30c7f0ee6cb1874

HERE="$(cd "$(dirname "$0")" && pwd)"
DEMOS_DIR="$(dirname "$HERE")"
CACHE="$HERE/.cache"
DIST="${OUT_DIR:-$HERE/dist}"

mkdir -p "$CACHE" "$DIST"

# --- 1. pyodide --------------------------------------------------------------
PYO_TGZ="$CACHE/pyodide-$PYODIDE_VERSION.tgz"
if [ ! -f "$PYO_TGZ" ]; then
  echo ">> fetching pyodide $PYODIDE_VERSION"
  curl -fsSL "https://registry.npmjs.org/pyodide/-/pyodide-$PYODIDE_VERSION.tgz" -o "$PYO_TGZ.tmp"
  mv "$PYO_TGZ.tmp" "$PYO_TGZ"
fi
mkdir -p "$DIST/pyodide"
tar -xzf "$PYO_TGZ" -C "$DIST/pyodide" --strip-components=1 \
  package/pyodide.mjs package/pyodide.asm.mjs package/pyodide.asm.wasm \
  package/python_stdlib.zip package/pyodide-lock.json
# Ship the ES modules as .js: browsers enforce a JavaScript MIME type on
# module imports and some static hosts (pgs.sh) serve .mjs as text/plain.
mv "$DIST/pyodide/pyodide.mjs" "$DIST/pyodide/pyodide.js"
mv "$DIST/pyodide/pyodide.asm.mjs" "$DIST/pyodide/pyodide.asm.js"
sed -i.bak 's/pyodide\.asm\.mjs/pyodide.asm.js/g' \
  "$DIST/pyodide/pyodide.js" "$DIST/pyodide/pyodide.asm.js"
rm -f "$DIST/pyodide/"*.bak

# --- 2. badge firmware + sim fakes -------------------------------------------
BADGE_TGZ="$CACHE/badge-$BADGE_SHA.tar.gz"
if [ ! -f "$BADGE_TGZ" ]; then
  echo ">> fetching badge-2024-software @ ${BADGE_SHA:0:9}"
  curl -fsSL "https://codeload.github.com/emfcamp/badge-2024-software/tar.gz/$BADGE_SHA" -o "$BADGE_TGZ.tmp"
  mv "$BADGE_TGZ.tmp" "$BADGE_TGZ"
fi

BADGE_SRC="$CACHE/badge-src"
rm -rf "$BADGE_SRC"
mkdir -p "$BADGE_SRC"
tar -xzf "$BADGE_TGZ" -C "$BADGE_SRC" --strip-components=1 \
  "badge-2024-software-$BADGE_SHA/modules" \
  "badge-2024-software-$BADGE_SHA/sim/fakes" \
  "badge-2024-software-$BADGE_SHA/sim/wasm/ctx.wasm" \
  "badge-2024-software-$BADGE_SHA/sim/background.png" \
  "badge-2024-software-$BADGE_SHA/LICENSE"

echo ">> assembling badge tree"
TREE="$CACHE/tree"
rm -rf "$TREE"
mkdir -p "$TREE"
cp -r "$BADGE_SRC/modules" "$TREE/modules"
cp -r "$BADGE_SRC/sim/fakes" "$TREE/fakes"
# Browser replacements (see overlay/*.py) + fakes that can't work here:
rm -f "$TREE/fakes/_sim.py" "$TREE/fakes/ctx.py" "$TREE/fakes/time.py" \
      "$TREE/fakes/urequests.py"
cp "$HERE/overlay/"*.py "$TREE/fakes/"

python3 - "$TREE" "$DIST/badge-tree.zip" <<'EOF'
import os, sys, zipfile
tree, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(tree):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, tree))
print(f"   badge-tree.zip: {os.path.getsize(out)//1024} KiB")
EOF

cp "$BADGE_SRC/sim/wasm/ctx.wasm" "$DIST/ctx.wasm"
cp "$BADGE_SRC/sim/background.png" "$DIST/badge.png"
cp "$BADGE_SRC/LICENSE" "$DIST/LICENSE-badge-2024-software.txt"
cp "$HERE/boot.py" "$DIST/boot.py"

# --- 3. demo sources + manifest -----------------------------------------------
echo ">> collecting demos"
mkdir -p "$DIST/demos"
python3 - "$DEMOS_DIR" "$DIST/demos" <<'EOF'
import json, os, re, shutil, sys
demos_dir, out = sys.argv[1], sys.argv[2]
entries = []
for name in os.listdir(demos_dir):
    app = os.path.join(demos_dir, name, "app.py")
    if not os.path.isfile(app):
        continue
    first = open(app).readline().strip()
    m = re.match(rf"#\s*{re.escape(name)}\s*\((\d+)\)\s*--\s*(.+)", first)
    if m:
        n = int(m.group(1))
        rest = m.group(2)
        title = rest.split(".")[0].strip()
        blurb = rest.strip()
    else:
        n, title, blurb = 999, name, ""
    shutil.copy(app, os.path.join(out, f"{name}.py"))
    entries.append({"id": name, "n": n, "title": title, "blurb": blurb})
entries.sort(key=lambda e: e["n"])
with open(os.path.join(out, "demos.json"), "w") as f:
    json.dump(entries, f, indent=1)
print(f"   {len(entries)} demos: " + ", ".join(e["id"] for e in entries))
EOF

# --- 3b. the one-file version: all code + mission, as markdown -----------------
echo ">> composing code.md"
python3 - "$DEMOS_DIR" "$HERE/src/code-intro.md" "$DIST/code.md" <<'EOF'
import json, os, re, sys
demos_dir, intro_path, out = sys.argv[1], sys.argv[2], sys.argv[3]

entries = []
for name in os.listdir(demos_dir):
    app = os.path.join(demos_dir, name, "app.py")
    if not os.path.isfile(app):
        continue
    src = open(app).read()
    # the opening comment wraps: join lines until the bare "#" separator
    head = []
    for line in src.split("\n"):
        if line.strip() == "#":
            break
        head.append(line.lstrip("# ").rstrip())
    first = " ".join(head)
    m = re.match(rf"{re.escape(name)}\s*\((\d+)\)\s*--\s*(.+)", first)
    if not m:
        continue
    n, rest = int(m.group(1)), m.group(2)
    title = rest.split(".")[0].strip()
    blurb = ".".join(rest.split(".")[1:]).strip().rstrip(".")
    prior = re.search(r"PRIOR ART.*?(https?://\S+)", src, re.S)
    entries.append({"n": n, "id": name, "title": title, "blurb": blurb,
                    "prior": prior.group(1) if prior else None, "src": src})
entries.sort(key=lambda e: e["n"])

parts = [open(intro_path).read().rstrip(), "", "## The programs", ""]
for e in entries:
    line = f"{e['n']}. **[{e['title']}](#{e['n']}--{e['id']})** — {e['blurb'] or e['id']}"
    parts.append(line)
parts.append("")

for e in entries:
    parts.append("---")
    parts.append("")
    parts.append(f"## {e['n']} · {e['id']}")
    parts.append("")
    links = [f"[play with it live](https://silvio-demos.pgs.sh/#{e['id']})"]
    if e["prior"]:
        links.append(f"[prior art]({e['prior']})")
    parts.append(f"**{e['title']}** · " + " · ".join(links))
    parts.append("")
    parts.append("```python")
    parts.append(e["src"].rstrip())
    parts.append("```")
    parts.append("")

open(out, "w").write("\n".join(parts) + "\n")
print(f"   code.md: {os.path.getsize(out)//1024} KiB, {len(entries)} programs")
EOF

# --- 4. bundle the JS -----------------------------------------------------------
echo ">> bundling editor + app (esbuild)"
cd "$HERE"
if [ ! -x node_modules/.bin/esbuild ]; then
  npm install --no-audit --no-fund
fi
BUILD_ID="$(date +%s)"
node_modules/.bin/esbuild src/app.js --bundle --format=esm --minify --target=es2020 \
  --define:__BUILD_ID__="\"$BUILD_ID\"" --outfile="$DIST/app.js"
node_modules/.bin/esbuild src/sim-worker.js --bundle --format=esm --minify --target=es2020 \
  --define:__BUILD_ID__="\"$BUILD_ID\"" --outfile="$DIST/sim-worker.js"

cp "$HERE/src/style.css" "$DIST/"
# Version the page's own entry points too, for caches that ignore no-store
# (and CDNs with long s-maxage, e.g. pgs.sh caches for a week).
sed -e "s/src=\"app.js\"/src=\"app.js?b=$BUILD_ID\"/" \
    -e "s/href=\"style.css\"/href=\"style.css?b=$BUILD_ID\"/" \
    "$HERE/src/index.html" > "$DIST/index.html"

echo ">> done: $DIST"
du -sh "$DIST" | sed 's/^/   /'
echo "   serve with: python3 $(basename "$HERE")/serve.py  (or any static host)"
