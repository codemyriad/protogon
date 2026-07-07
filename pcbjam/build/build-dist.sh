#!/usr/bin/env bash
# Build a fully self-contained static site: pcbjam (KiCad PCBnew in the browser)
# preloaded with the Protogon board, with WASM and 3D component models bundled so
# there is ZERO runtime dependency on cdn.pcbjam.com. The result (a plain dist/
# tree) can be served by any static host — it is what the Docker image bakes in
# and what deploy-bunny.sh uploads to a BunnyCDN bucket.
#
# Nothing here compiles KiCad: the ~200 MB of prebuilt WASM and the handful of
# 3D model bodies the board actually references are DOWNLOADED from pcbjam's
# public, CORS-open CDN at build time and copied same-origin into dist/. Only the
# small React/Vite shell (@pcbjam/standalone) is built from source.
#
# Runs the same whether invoked by pcbjam/Dockerfile or directly on a dev box
# (needs: node >=20, corepack, git, curl, jq, sha256sum).
#
#   BOARD_SRC=/path/to/protogon-repo OUT_DIR=./dist ./build-dist.sh
#
# Env knobs (all optional; defaults pin the reviewed release):
#   PCBJAM_TAG   pcbjam git tag to build the app from        (default v0.1.6.2)
#   WASM_VER     prebuilt WASM tool version on the CDN        (default v0.1.5)
#   MODELS_TAG   kicad-models snapshot tag on the CDN         (default 10.0.3)
#   CDN          pcbjam asset CDN origin                      (default https://cdn.pcbjam.com)
#   BOARD_SRC    dir holding codemyriad-protogon.kicad_pcb    (default: repo root, two levels up)
#   BUILD_DIR    scratch dir (pcbjam clone + node_modules)    (default: $PWD/.pcbjam-build)
#   OUT_DIR      where the finished dist/ is copied           (default: $BUILD_DIR/dist)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

PCBJAM_TAG="${PCBJAM_TAG:-v0.1.6.2}"
WASM_VER="${WASM_VER:-v0.1.5}"
MODELS_TAG="${MODELS_TAG:-10.0.3}"
CDN="${CDN:-https://cdn.pcbjam.com}"
CDN="${CDN%/}"
BOARD_SRC="${BOARD_SRC:-$REPO_ROOT}"
BUILD_DIR="${BUILD_DIR:-$PWD/.pcbjam-build}"
OUT_DIR="${OUT_DIR:-$BUILD_DIR/dist}"

PCBJAM_DIR="$BUILD_DIR/pcbjam"
STAGE="$PCBJAM_DIR/.gallery-src/codemyriad-protogon"   # gallery.json `root` points here
SLUG="codemyriad-protogon"

# Subpath the whole site is served under (e.g. SITE_BASE=/board-editor/). Default
# is the domain root. Normalised to a leading+trailing slash; BASEP is the
# no-trailing-slash form ("" at root) used to prefix same-origin asset URLs.
SITE_BASE="${SITE_BASE:-/}"
_b="${SITE_BASE#/}"; _b="${_b%/}"
if [ -z "$_b" ]; then SITE_BASE="/"; BASEP=""; else SITE_BASE="/$_b/"; BASEP="/$_b"; fi
DEEPLINK="$BASEP/demo/projects/$SLUG/$SLUG.kicad_pcb"      # full path (host redirects, output)
DEEPLINK_REL="/demo/projects/$SLUG/$SLUG.kicad_pcb"       # basename-relative (React Router adds the base)

# Use the pnpm version pcbjam pins (packageManager field) via corepack, without a
# global `corepack enable` (which needs write access to Node's bin dir). This form
# works both in the Docker build and on a plain dev box.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
PNPM_PM="pnpm@10.33.0"   # overwritten from pcbjam's packageManager field after checkout
pnpm() { ( cd "$PCBJAM_DIR" && corepack "$PNPM_PM" "$@" ); }

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

for bin in node corepack git curl jq sha256sum; do
  command -v "$bin" >/dev/null 2>&1 || die "missing required tool: $bin"
done

# The three custom STEP models are git-LFS objects in the protogon repo. If they
# are still pointer files the 3D view of the Qwiic/EEPROM/jumper is silently
# wrong, so fail loudly instead.
for f in \
  "$BOARD_SRC/codemyriad-protogon.kicad_pcb" \
  "$BOARD_SRC/JLC2KiCad_lib/footprint/packages3d/CONN-SMD_4P-P1.00_SM04B-SRSS-TB-LF-SN.step" \
  "$BOARD_SRC/JLC2KiCad_lib/footprint/packages3d/TSSOP-8_L4.4-W3.0-P0.65-LS6.4-BL.step" \
  "$BOARD_SRC/JLC2KiCad_lib/footprint/packages3d/HDR-TH_2P-P2.54-V-M.step"; do
  [ -f "$f" ] || die "board source not found: $f (is BOARD_SRC correct?)"
done
if head -c 64 "$BOARD_SRC/JLC2KiCad_lib/footprint/packages3d/TSSOP-8_L4.4-W3.0-P0.65-LS6.4-BL.step" \
     | grep -q 'git-lfs.github.com'; then
  die "3D model STEP files are unresolved git-LFS pointers. Run: git lfs pull -I 'JLC2KiCad_lib/footprint/packages3d/*.step'"
fi

mkdir -p "$BUILD_DIR"

# --- 1. pcbjam checkout (app source only; NOT the KiCad/wx WASM submodules) ----
log "pcbjam @ $PCBJAM_TAG"
if [ ! -d "$PCBJAM_DIR/.git" ]; then
  git clone --depth 1 --branch "$PCBJAM_TAG" \
    https://github.com/emergence-engineering/pcbjam "$PCBJAM_DIR"
fi
# @pcbjam/shared + @pcbjam/sync-client are consumed as TS source from this one
# submodule; the kicad/wxwidgets/binaryen submodules are only for compiling WASM
# from source and are deliberately skipped (we use prebuilt WASM).
git -C "$PCBJAM_DIR" submodule update --init --depth 1 web/pcbjam-shared

# Pin the exact pnpm the release expects (corepack's direct form ignores the
# packageManager field, so read it and pass it explicitly).
_pm="$(node -p "require('$PCBJAM_DIR/package.json').packageManager" 2>/dev/null || true)"
case "$_pm" in pnpm@*) PNPM_PM="$_pm" ;; esac
echo "using $PNPM_PM"

# --- 2. install workspace deps -------------------------------------------------
log "pnpm install"
pnpm --dir web install --frozen-lockfile

# --- 3. stage the Protogon project as the one gallery entry --------------------
# publish-content joins gallery.json `root` + each `files[]` path and reuses that
# path as the in-browser MEMFS path. The board references its custom models by the
# bare relative path "packages3d/<name>.step", and KiCad's FILENAME_RESOLVER looks
# them up against the project directory FIRST — so they must sit at packages3d/*
# next to the board (NOT under JLC2KiCad_lib/...).
log "stage board + custom models"
rm -rf "$STAGE"
mkdir -p "$STAGE/packages3d"
cp "$BOARD_SRC/codemyriad-protogon.kicad_pcb" "$STAGE/"
cp "$BOARD_SRC/codemyriad-protogon.kicad_pro" "$STAGE/" 2>/dev/null || true
cp "$BOARD_SRC"/JLC2KiCad_lib/footprint/packages3d/*.step "$STAGE/packages3d/"

# --- 3c. teach boot.ts to load a split wasm (for hosts with a per-file size cap,
#         e.g. pgs.sh's 100MB). Inert unless a `<wasm>.parts.json` is present, so
#         the normal single-file path is untouched. Applied to the checkout before
#         the bundle is built; idempotent via the PCBJAM_WASM_PARTS marker. --------
log "patch boot.ts (split-wasm support)"
python3 - "$PCBJAM_DIR/web/standalone/src/wasm/boot.ts" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
if "PCBJAM_WASM_PARTS" in s:
    print("  already patched"); raise SystemExit(0)
anchor = "): Promise<Response> {\n  const res = await fetch(url);"
if anchor not in s:
    raise SystemExit("ERROR: boot.ts anchor not found (pcbjam layout changed?)")
inject = '''): Promise<Response> {
  // PCBJAM_WASM_PARTS: if `<url>.parts.json` exists, the wasm was split to fit a
  // host's per-file size cap (pgs.sh = 100MB); fetch the parts and concatenate.
  // Otherwise fall through to the normal single-file fetch below.
  try {
    const _pm = await fetch(url + ".parts.json", { cache: "no-store" });
    if (_pm.ok) {
      const _txt = await _pm.text();
      if (_txt.trimStart().startsWith("{")) {
        const _m = JSON.parse(_txt);
        const _dir = url.slice(0, url.lastIndexOf("/") + 1);
        const _buf = new Uint8Array(_m.size);
        let _off = 0;
        for (const _p of _m.parts) {
          const _r = await fetch(_dir + _p);
          if (!_r.ok) throw new Error("HTTP " + _r.status + " fetching " + _p);
          const _b = new Uint8Array(await _r.arrayBuffer());
          _buf.set(_b, _off);
          _off += _b.byteLength;
          if (onProgress) onProgress(_off, _m.size);
        }
        return new Response(_buf, { headers: { "content-type": "application/octet-stream" } });
      }
    }
  } catch (_e) { /* fall through to the single-file fetch */ }
  const res = await fetch(url);'''
open(p, "w").write(s.replace(anchor, inject, 1))
print("  patched")
PY

# Make React Router honour the deploy subpath (Vite's base -> import.meta.env.BASE_URL).
# Harmless at the root ("/" is the default basename); required under a subpath.
log "patch main.tsx (router basename)"
python3 - "$PCBJAM_DIR/web/standalone/src/main.tsx" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
if "basename=" in s:
    print("  already patched"); raise SystemExit(0)
if "<BrowserRouter>" not in s:
    raise SystemExit("ERROR: main.tsx <BrowserRouter> not found")
open(p, "w").write(s.replace("<BrowserRouter>", "<BrowserRouter basename={import.meta.env.BASE_URL}>", 1))
print("  patched")
PY

# Open the board straight from the app root, client-side: the "/" route redirects
# to the board instead of showing the gallery. Host-agnostic (works at root or
# under a subpath), so no fragile host redirect rule is needed to "just open it".
log "patch App.tsx (auto-open the board at the app root)"
python3 - "$PCBJAM_DIR/web/standalone/src/App.tsx" "$DEEPLINK_REL" <<'PY'
import re, sys
p, target = sys.argv[1], sys.argv[2]
s = open(p).read()
if "PROTOGON_AUTO_OPEN" in s:
    print("  already patched"); raise SystemExit(0)
m = re.search(r'import\s*\{([^}]*)\}\s*from\s*"react-router-dom";', s)
if not m:
    raise SystemExit("ERROR: react-router-dom import not found in App.tsx")
if "Navigate" not in m.group(1):
    s = s[:m.start(1)] + m.group(1).rstrip() + ", Navigate " + s[m.end(1):]
old = '<Route path="/" element={<HomePage />} />'
if old not in s:
    raise SystemExit("ERROR: home route not found in App.tsx")
s = s.replace(old, '<Route path="/" element={<Navigate to="%s" replace />} /> {/* PROTOGON_AUTO_OPEN */}' % target, 1)
open(p, "w").write(s)
print("  patched")
PY

# --- 4. build the standalone, pinned same-origin (bypasses build-demo.mjs, which
#        hardwires everything to cdn.pcbjam.com and strips dist/wasm) ------------
log "vite build (@pcbjam/standalone)"
GIT_SHA="$(git -C "$BOARD_SRC" rev-parse HEAD 2>/dev/null || echo protogon)"
# Versioned WASM dir: VITE_WASM_ROOT=/wasm/<ver> (no VITE_WASM_MANIFEST) -> the app
# loads every WASM file from that immutable path. The <ver> segment is a semantic,
# content-changing URL: bump WASM_VER and every asset gets a new URL, so the old
# ones stay cached forever (_headers marks /wasm/* immutable). See mirror step 6.
(
  export VITE_PROJECT_SOURCE=static
  export VITE_PROJECT_MANIFEST_URL="$BASEP/content/protogon/manifest.json"
  export VITE_LOCAL_PROJECTS=idb
  export VITE_LIBS_SOURCE=static
  export VITE_WASM_ROOT="$BASEP/wasm/$WASM_VER"
  export VITE_MODELS_MANIFEST_URL="$BASEP/libs/kicad-models/$MODELS_TAG/manifest.json"
  export VITE_YJS_PROVIDER=broadcastchannel
  export VITE_DOC_SOURCE=api
  export VITE_API_BASE_URL=http://offline.invalid
  export VITE_APP_TAG=protogon
  export VITE_GIT_SHA="$GIT_SHA"
  export VITE_REPO_URL=https://github.com/codemyriad/protogon
  pnpm --dir web --filter @pcbjam/standalone exec vite build --base "$SITE_BASE"
)

DIST="$PCBJAM_DIR/web/standalone/dist"
[ -f "$DIST/index.html" ] || die "vite build produced no dist/index.html"

# --- 5. publish the gallery (board bytes + manifest) into dist/content ---------
log "publish gallery content"
( cd "$PCBJAM_DIR" && node scripts/deploy/publish-content.mjs \
    --tag protogon --gallery "$HERE/gallery.json" \
    --driver local --out "$PCBJAM_DIR/.cdn-out" )
rm -rf "$DIST/content"
cp -a "$PCBJAM_DIR/.cdn-out/content" "$DIST/content"

# --- 6. mirror the prebuilt WASM (flat, same-origin) --------------------------
# .wasm/.js are stored br-compressed on the CDN; --compressed writes the real
# decompressed bytes (the static host re-compresses on the fly). images.tar.gz is
# raw gzip KiCad gunzips itself, so it must be copied verbatim (NO --compressed).
log "mirror WASM -> dist/wasm/$WASM_VER (versioned, immutable)"
WD="$DIST/wasm/$WASM_VER"; mkdir -p "$WD"
verify_sha() { # <file> <expected sha256: prefixed>
  local got; got="sha256:$(sha256sum "$1" | cut -d' ' -f1)"
  [ "$got" = "$2" ] || die "checksum mismatch for $1 (got $got want $2)"
}
fetch_wasm_bundle() { # <bundle> <compressed-file...> -- special-cases images.tar.gz
  local bundle="$1"; shift
  local base="$CDN/wasm/$bundle/$WASM_VER"
  local meta; meta="$(curl -fsSL "$base/meta.json")"
  for f in "$@"; do
    if [ "$f" = "images.tar.gz" ]; then
      curl -fsSL              "$base/$f" -o "$WD/$f"     # raw gzip, keep as-is
    else
      curl -fsSL --compressed "$base/$f" -o "$WD/$f"
    fi
    local want; want="$(jq -r --arg k "$f" '.files[$k]' <<<"$meta")"
    [ "$want" = "null" ] || verify_sha "$WD/$f" "$want"
  done
}
fetch_wasm_bundle kicad_editor kicad_editor.wasm kicad_editor.js wx.js wx-dom.js images.tar.gz
fetch_wasm_bundle occ_service  occ_service.wasm occ_service.js

# --- 7. mirror ONLY the 3D model bodies the board references ------------------
# Stock models (resistors, cap, LED, pin-header) come from the sparse kicad-models
# CDN; the 3 custom models were already staged as project files in step 3. The
# board references the pin header as .wrl but the 10.0.3 set is STEP-only — the
# app's models-bridge falls back .wrl -> .step, so we mirror the .step body.
log "mirror 3D models -> dist/libs/kicad-models ($MODELS_TAG)"
MROOT="$DIST/libs/kicad-models"
mkdir -p "$MROOT/$MODELS_TAG" "$MROOT/blobs/sha256"
# top manifest, trimmed to the 4 libs we actually use
curl -fsSL --compressed "$CDN/libs/kicad-models/$MODELS_TAG/manifest.json" \
  | jq '{schema, tag, libs: [.libs[] | select(.id | IN("Resistor_SMD","Capacitor_SMD","LED_SMD","Connector_PinHeader_2.54mm"))]}' \
  > "$MROOT/$MODELS_TAG/manifest.json"
mirror_model() { # <lib> <item-path...>   e.g. Resistor_SMD model3d/R_0603_1608Metric.step
  local lib="$1"; shift
  local full; full="$(curl -fsSL --compressed "$CDN/libs/kicad-models/$MODELS_TAG/$lib/manifest")"
  local trimmed='{"version":1,"entries":{}}'
  for item in "$@"; do
    local hash size
    hash="$(jq -r --arg p "$item" '.entries[$p].hash // empty' <<<"$full")"
    size="$(jq -r --arg p "$item" '.entries[$p].size // 0'    <<<"$full")"
    [ -n "$hash" ] || die "model item not on CDN: $lib/$item"
    trimmed="$(jq --arg p "$item" --arg h "$hash" --argjson s "$size" \
                  '.entries[$p]={hash:$h,size:$s,mtime:0}' <<<"$trimmed")"
    curl -fsSL --compressed "$CDN/libs/kicad-models/blobs/sha256/$hash" \
      -o "$MROOT/blobs/sha256/$hash"
  done
  mkdir -p "$MROOT/$MODELS_TAG/$lib"
  printf '%s\n' "$trimmed" > "$MROOT/$MODELS_TAG/$lib/manifest"
}
mirror_model Resistor_SMD               model3d/R_0603_1608Metric.step
mirror_model Capacitor_SMD              model3d/C_0603_1608Metric.step
mirror_model LED_SMD                    model3d/LED_0805_2012Metric.step
mirror_model Connector_PinHeader_2.54mm model3d/PinHeader_2x10_P2.54mm_Vertical.step

# --- 7b. static-host rules for hosts that read Cloudflare-style control files
#         (pgs.sh, Cloudflare Pages, Netlify). The Docker/nginx path ignores
#         these; nginx.conf does the same job there. -----------------------------
log "write _headers / _redirects"
{
  # Under a subpath, send the domain root and the bare (no-slash) subpath into the
  # app. These are EXACT matches (no force, no wildcard) so they never shadow the
  # real asset files under the subpath. The board auto-opens client-side via the
  # App.tsx "/" route, so no deep-link redirect is needed here.
  if [ -n "$BASEP" ]; then
    echo "/          $BASEP/    302"
    echo "$BASEP     $BASEP/    302"
  fi
  echo "$BASEP/*   $BASEP/index.html    200"  # SPA fallback (file-first: real assets win)
} > "$DIST/_redirects"
# /wasm/* and the content-addressed model blobs are versioned/immutable, so cache
# them forever; a version bump changes the URL. (.wasm/.gz content-types come from
# the host's own extension map; pgs.sh serves .wasm as application/wasm+gzip and
# .gz as octet-stream raw, which is exactly what we need.)
{
  # IMPORTANT: pgs.sh does NOT accumulate _headers rules — the most specific
  # matching path wins and REPLACES less specific ones. So the COOP/COEP/CORP
  # isolation headers MUST be repeated in every rule, or the /wasm/* files lose
  # them and KiCad's pthread worker scripts stall under COEP require-corp.
  iso() { echo "  Cross-Origin-Opener-Policy: same-origin"
          echo "  Cross-Origin-Embedder-Policy: require-corp"
          echo "  Cross-Origin-Resource-Policy: cross-origin"; }
  echo "/*"; iso
  echo "$BASEP/wasm/*"; iso; echo "  Cache-Control: public, max-age=31536000, immutable"
  echo "$BASEP/libs/kicad-models/blobs/*"; iso; echo "  Cache-Control: public, max-age=31536000, immutable"
} > "$DIST/_headers"

# --- 7c. split the big editor wasm for hosts with a per-file size cap (pgs.sh =
#         100MB; kicad_editor.wasm is ~130MB). Parts are named *.wasm so the host
#         still serves them application/wasm (gzipped on the fly); the patched
#         boot.ts fetches <wasm>.parts.json and concatenates. Gated on
#         WASM_SPLIT_MB — set it for pgs.sh, leave unset for Docker/nginx. --------
if [ -n "${WASM_SPLIT_MB:-}" ] && [ -f "$WD/kicad_editor.wasm" ]; then
  log "split kicad_editor.wasm into ${WASM_SPLIT_MB}MiB parts"
  sz="$(stat -c%s "$WD/kicad_editor.wasm")"
  ( cd "$WD" && split -b "${WASM_SPLIT_MB}m" -d -a 1 kicad_editor.wasm kicad_editor.part )
  parts='[]'
  for f in "$WD"/kicad_editor.part[0-9]*; do
    mv "$f" "$f.wasm"
    parts="$(jq -c --arg n "$(basename "$f").wasm" '. + [$n]' <<<"$parts")"
  done
  printf '{"parts":%s,"size":%s}\n' "$parts" "$sz" > "$WD/kicad_editor.wasm.parts.json"
  rm -f "$WD/kicad_editor.wasm"
  echo "  -> $(cd "$WD" && ls kicad_editor.part*.wasm | tr '\n' ' ')+ parts.json"
fi

# --- 8. publish the finished tree ---------------------------------------------
if [ "$OUT_DIR" != "$DIST" ]; then
  log "copy dist -> $OUT_DIR"
  rm -rf "$OUT_DIR"; mkdir -p "$OUT_DIR"
  cp -a "$DIST/." "$OUT_DIR/"
fi

log "done"
echo "  static site : $OUT_DIR"
echo "  entry route : $DEEPLINK"
echo "  size        : $(du -sh "$OUT_DIR" | cut -f1)"
