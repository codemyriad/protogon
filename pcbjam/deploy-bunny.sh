#!/usr/bin/env bash
# Push the built static site to a BunnyCDN Storage Zone.
#
# The site bytes come out of the GHCR image (the "built artifact"), so this
# deploys exactly what `run.sh` serves. After uploading, it prints the Pull Zone
# settings BunnyCDN needs — Bunny does NOT read nginx.conf, so the COOP/COEP
# headers, the *.wasm / images.tar.gz content rules, the SPA fallback, and the
# "/" -> board redirect must be set as Pull Zone headers / Edge Rules.
#
# Required env:
#   BUNNY_STORAGE_ZONE       storage zone name
#   BUNNY_STORAGE_PASSWORD   storage zone password (read/write access key)
# Optional env:
#   BUNNY_STORAGE_ENDPOINT   region host (default storage.bunnycdn.com; e.g. ny./la./sg.)
#   BUNNY_TARGET_PATH        subfolder in the zone (default "" = root)
#   IMAGE                    GHCR image to extract from (default ghcr.io/codemyriad/protogon-pcbjam:latest)
#   DIST                     use this prebuilt dir instead of extracting from the image
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-ghcr.io/codemyriad/protogon-pcbjam:latest}"
ENDPOINT="${BUNNY_STORAGE_ENDPOINT:-storage.bunnycdn.com}"
TARGET="${BUNNY_TARGET_PATH:-}"
TARGET="${TARGET#/}"; TARGET="${TARGET%/}"

: "${BUNNY_STORAGE_ZONE:?set BUNNY_STORAGE_ZONE}"
: "${BUNNY_STORAGE_PASSWORD:?set BUNNY_STORAGE_PASSWORD}"

DEEPLINK="/demo/projects/codemyriad-protogon/codemyriad-protogon.kicad_pcb"

# --- 1. obtain the static site --------------------------------------------------
CLEAN_DIST=0
if [ -z "${DIST:-}" ]; then
  command -v docker >/dev/null 2>&1 || { echo "docker required to extract $IMAGE (or set DIST=)" >&2; exit 1; }
  docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"
  DIST="$(mktemp -d)/dist"; CLEAN_DIST=1
  cid="$(docker create "$IMAGE")"
  docker cp "$cid:/usr/share/nginx/html/." "$DIST"
  docker rm "$cid" >/dev/null
fi
[ -f "$DIST/index.html" ] || { echo "no index.html under $DIST" >&2; exit 1; }

# --- 2. upload every file (BunnyCDN Storage HTTP API) ---------------------------
base="https://$ENDPOINT/$BUNNY_STORAGE_ZONE${TARGET:+/$TARGET}"
echo "==> uploading $DIST -> $base"
count=0
while IFS= read -r -d '' f; do
  rel="${f#"$DIST"/}"
  curl -fsS -X PUT "$base/$rel" \
    -H "AccessKey: $BUNNY_STORAGE_PASSWORD" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$f" >/dev/null
  count=$((count + 1))
  printf '\r    %d files' "$count"
done < <(find "$DIST" -type f -print0)
echo; echo "==> uploaded $count files"
[ "$CLEAN_DIST" = 1 ] && rm -rf "$(dirname "$DIST")"

# --- 3. one-time Pull Zone configuration (print, don't automate) ----------------
cat <<EOF

Next, in the BunnyCDN Pull Zone that fronts this Storage Zone (once):

  Headers tab -> add these response headers to ALL responses:
      Cross-Origin-Opener-Policy: same-origin
      Cross-Origin-Embedder-Policy: require-corp
    (Required for KiCad's SharedArrayBuffer/threads; without them nothing boots.)

  Edge Rules:
    1. "Set Response Header" Content-Type = application/wasm   when URL ends with .wasm
    2. "Set Response Header" Content-Type = application/octet-stream   when URL ends with .tar.gz
       (and do NOT enable Content-Encoding / compression on .tar.gz — it is raw
        gzip KiCad decompresses itself)
    3. "Set Response Header" Content-Type = application/json   when URL matches */libs/kicad-models/*/manifest
    4. SPA fallback: serve /index.html (200) for unknown paths
       (Pull Zone -> "Error Pages" -> enable single-page-app / custom 404 = /index.html)
    5. "Redirect" 302 from "/" to $DEEPLINK   (so the domain root opens the board)

  Then purge the zone cache.

Live URL after that: https://<your-pull-zone-host>/  (redirects into the board)
EOF
