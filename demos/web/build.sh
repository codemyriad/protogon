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
# mpy-cross compiled to wasm (MIT, pybricks) — emits pure-bytecode .mpy v6.0,
# loadable by any v6 firmware incl. the Tildagon pin (MicroPython 1.28.0).
MPYCROSS_VERSION=2.0.0
MPYCROSS_SHA256=a861d4fe8dff977536575c39c9ec7072e7e9bdd39846e113148920a10117181d

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

# --- 2b. fonts (IBM Plex, vendored so the site stays zero-CDN) ----------------
# Latin subsets from Google Fonts; gstatic files are content-addressed, so the
# URLs are stable and the checksums pin them. Sans is the variable font (one
# file covers weights 100-700); Mono needs one file per weight.
echo ">> fonts (IBM Plex)"
mkdir -p "$DIST/fonts"
while read -r name url sha; do
  [ -z "$name" ] && continue
  f="$CACHE/$name"
  if [ ! -f "$f" ]; then
    curl -fsSL "$url" -o "$f.tmp"
    echo "$sha  $f.tmp" | sha256sum -c - >/dev/null
    mv "$f.tmp" "$f"
  fi
  cp "$f" "$DIST/fonts/$name"
done <<'FONTS'
plex-sans-var.woff2 https://fonts.gstatic.com/s/ibmplexsans/v23/zYXzKVElMYYaJe8bpLHnCwDKr932-G7dytD-Dmu1syxeKYY.woff2 e2291e842cf5af167122a22881a740c7f2dda7716f1e8cd76680264f4a859470
plex-mono-400.woff2 https://fonts.gstatic.com/s/ibmplexmono/v20/-F63fjptAgt5VM-kVkqdyU8n1i8q1w.woff2 08949f728dc52d528e69b1667d15c89a5686a4ee9a296ff90983985f99c380f7
plex-mono-500.woff2 https://fonts.gstatic.com/s/ibmplexmono/v20/-F6qfjptAgt5VM-kVkqdyU8n3twJwlBFgg.woff2 01d285447409c8a588692162439a038b8cbd7871309ee20267b0d2d91c6e8e22
plex-mono-600.woff2 https://fonts.gstatic.com/s/ibmplexmono/v20/-F6qfjptAgt5VM-kVkqdyU8n3vAOwlBFgg.woff2 0d1f0b8d0722224e32e9f28261bdc86c79115be73444ae5eceb73976a1bcdf83
FONTS

# --- 3. demo sources + manifest -----------------------------------------------
echo ">> collecting demos"
rm -rf "$DIST/demos"   # else renamed/removed demos linger from an earlier build
mkdir -p "$DIST/demos"
python3 - "$DEMOS_DIR" "$DIST/demos" <<'EOF'
import json, os, re, shutil, sys
demos_dir, out = sys.argv[1], sys.argv[2]
entries = []
missing_previews = []
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
    # Bundled gallery thumbnail: an emulator-captured frame, committed next
    # to the demo (regenerate via renderPreviewPack — see src/README).
    preview = os.path.join(demos_dir, name, "preview.png")
    if os.path.isfile(preview):
        shutil.copy(preview, os.path.join(out, f"{name}.png"))
    else:
        missing_previews.append(name)
    entries.append({"id": name, "n": n, "title": title, "blurb": blurb})
entries.sort(key=lambda e: e["n"])
with open(os.path.join(out, "demos.json"), "w") as f:
    json.dump(entries, f, indent=1)
print(f"   {len(entries)} demos: " + ", ".join(e["id"] for e in entries))
if missing_previews:
    print("   WARNING: no preview.png (gallery shows a skeleton tile): "
          + ", ".join(sorted(missing_previews)))
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
    prior = re.search(r"(?:See also:|Credits:).*?(https?://\S+)", src, re.S)
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
        links.append(f"[see also]({e['prior']})")
    parts.append(f"**{e['title']}** · " + " · ".join(links))
    parts.append("")
    parts.append("```python")
    parts.append(e["src"].rstrip())
    parts.append("```")
    parts.append("")

open(out, "w").write("\n".join(parts) + "\n")
print(f"   code.md: {os.path.getsize(out)//1024} KiB, {len(entries)} programs")
EOF

# --- 3c. hardware bring-up notes ------------------------------------------------
cp "$HERE/hardware-notes.md" "$DIST/hardware-notes.md"

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

# --- 4b. mpy-cross (wasm) --------------------------------------------------------
# The npm package ships a CommonJS wrapper + Emscripten UMD glue; esbuild
# re-wraps them as one browser ES module. The wasm is fetched at runtime via
# the URL flash.js passes as compile()'s 4th argument.
MPY_TGZ="$CACHE/mpy-cross-v6-$MPYCROSS_VERSION.tgz"
if [ ! -f "$MPY_TGZ" ]; then
  echo ">> fetching @pybricks/mpy-cross-v6 $MPYCROSS_VERSION"
  curl -fsSL "https://registry.npmjs.org/@pybricks/mpy-cross-v6/-/mpy-cross-v6-$MPYCROSS_VERSION.tgz" -o "$MPY_TGZ.tmp"
  echo "$MPYCROSS_SHA256  $MPY_TGZ.tmp" | sha256sum -c - >/dev/null
  mv "$MPY_TGZ.tmp" "$MPY_TGZ"
fi
MPY_SRC="$CACHE/mpy-cross-src"
rm -rf "$MPY_SRC"
mkdir -p "$MPY_SRC"
tar -xzf "$MPY_TGZ" -C "$MPY_SRC" --strip-components=1 \
  package/build/index.js package/build/mpy-cross-v6.js package/build/mpy-cross-v6.wasm package/LICENSE
mkdir -p "$DIST/mpy-cross"
node_modules/.bin/esbuild "$MPY_SRC/build/index.js" --bundle --format=esm --minify \
  --platform=browser --target=es2020 --external:fs --external:path \
  --outfile="$DIST/mpy-cross/index.js"
cp "$MPY_SRC/build/mpy-cross-v6.wasm" "$DIST/mpy-cross/mpy-cross-v6.wasm"
cp "$MPY_SRC/LICENSE" "$DIST/mpy-cross/LICENSE.txt"

cp "$HERE/src/style.css" "$DIST/"
# Version the page's own entry points too, for caches that ignore no-store
# (and CDNs with long s-maxage, e.g. pgs.sh caches for a week).
sed -e "s/src=\"app.js\"/src=\"app.js?b=$BUILD_ID\"/" \
    -e "s/href=\"style.css\"/href=\"style.css?b=$BUILD_ID\"/" \
    "$HERE/src/index.html" > "$DIST/index.html"

echo ">> done: $DIST"
du -sh "$DIST" | sed 's/^/   /'
echo "   serve with: python3 $(basename "$HERE")/serve.py  (or any static host)"
