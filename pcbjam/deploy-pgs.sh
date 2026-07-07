#!/usr/bin/env bash
# Build the split, self-contained static site and deploy it to a pico.sh pgs.sh
# project over rsync.
#
# Two pgs.sh constraints drive the shape of this:
#   - 100MB per-file cap  -> build-dist.sh splits the ~130MB editor wasm into
#     parts the patched loader reassembles (still no cdn.pcbjam.com at runtime).
#   - _headers/_redirects are read from the PROJECT ROOT only -> when serving under
#     a subpath (SITE_BASE), the app files go under that subpath but the control
#     files are placed at the project root.
#
#   ./pcbjam/deploy-pgs.sh                       # -> https://<user>-protogon-kicad.pgs.sh/board-editor/
#   PROJECT=foo SITE_BASE=/ ./pcbjam/deploy-pgs.sh   # serve at the domain root instead
#
# Env: PROJECT (default protogon-kicad), SITE_BASE (default /board-editor/),
#      WASM_SPLIT_MB (default 90), DIST (skip the build and deploy this dir).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

PROJECT="${PROJECT:-protogon-kicad}"
SITE_BASE="${SITE_BASE:-/board-editor/}"
WASM_SPLIT_MB="${WASM_SPLIT_MB:-90}"

case "$PROJECT" in *[!a-z0-9-]*|"") echo "pgs.sh project name must match [a-z0-9-]: '$PROJECT'" >&2; exit 1;; esac

# Normalise SITE_BASE -> BASEP (no trailing slash, "" at root), same as build-dist.sh.
_b="${SITE_BASE#/}"; _b="${_b%/}"
if [ -z "$_b" ]; then SITE_BASE="/"; BASEP=""; else SITE_BASE="/$_b/"; BASEP="/$_b"; fi

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# --- build (unless a prebuilt DIST was handed in) ------------------------------
if [ -z "${DIST:-}" ]; then
  DIST="$WORK/dist"
  echo "==> build (SITE_BASE=$SITE_BASE, WASM_SPLIT_MB=$WASM_SPLIT_MB)"
  BOARD_SRC="$REPO_ROOT" OUT_DIR="$DIST" SITE_BASE="$SITE_BASE" WASM_SPLIT_MB="$WASM_SPLIT_MB" \
    bash "$HERE/build/build-dist.sh"
fi
[ -f "$DIST/index.html" ] || { echo "no index.html under $DIST" >&2; exit 1; }

# --- lay out the project tree, then one --delete rsync -------------------------
SITEROOT="$WORK/site"; mkdir -p "$SITEROOT"
if [ -z "$BASEP" ]; then
  cp -a "$DIST/." "$SITEROOT/"
else
  mkdir -p "$SITEROOT$BASEP"
  cp -a "$DIST/." "$SITEROOT$BASEP/"
  # pgs.sh only reads _headers/_redirects at the project root.
  mv "$SITEROOT$BASEP/_headers"   "$SITEROOT/_headers"
  mv "$SITEROOT$BASEP/_redirects" "$SITEROOT/_redirects"
fi

echo "==> rsync --delete -> pgs.sh:/$PROJECT"
host="$(rsync --delete -r -e "ssh -o BatchMode=yes" "$SITEROOT/" "pgs.sh:/$PROJECT" 2>&1 \
          | grep -oE 'https://[a-z0-9-]+\.pgs\.sh' | head -1)"

# The assets are Cache-Control: immutable, so pgs.sh edge-caches them WITH their
# response headers. Purge, or a redeploy that changed headers keeps serving the
# old ones (this is what made the wasm ship without COOP/COEP once).
echo "==> purge edge cache"
ssh -o BatchMode=yes pgs.sh cache "$PROJECT" --write 2>&1 | head -1 || true

echo "==> deployed: ${host:-https://<user>-$PROJECT.pgs.sh}$BASEP/"
