#!/usr/bin/env bash
# Open the Protogon board in pcbjam (browser KiCad), fully offline.
#
# Pulls the prebuilt image from GHCR and runs it; falls back to building it
# locally (pcbjam/Dockerfile) if the pull fails or --build is given. Then opens a
# browser at http://localhost:<port>/ which lands straight in the PCB editor.
#
#   ./pcbjam/run.sh                # pull (or build) and open
#   ./pcbjam/run.sh --build        # always build locally
#   ./pcbjam/run.sh --port 9000    # different host port
#   ./pcbjam/run.sh --no-open      # don't launch a browser
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

IMAGE="${IMAGE:-ghcr.io/codemyriad/protogon-pcbjam:latest}"
PORT="${PORT:-8080}"
NAME="protogon-pcbjam"
FORCE_BUILD=0
OPEN=1

while [ $# -gt 0 ]; do
  case "$1" in
    --build)   FORCE_BUILD=1 ;;
    --port)    PORT="$2"; shift ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker daemon is not running" >&2; exit 1; }

build_local() {
  echo "==> building $IMAGE locally"
  # The custom 3D models are git-LFS objects; make sure they are real files.
  if command -v git-lfs >/dev/null 2>&1; then
    git -C "$REPO_ROOT" lfs pull -I 'JLC2KiCad_lib/footprint/packages3d/*.step' 2>/dev/null || true
  fi
  DOCKER_BUILDKIT=1 docker build -f "$HERE/Dockerfile" -t "$IMAGE" "$REPO_ROOT"
}

if [ "$FORCE_BUILD" = 1 ]; then
  build_local
elif ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "==> pulling $IMAGE"
  docker pull "$IMAGE" || { echo "==> pull failed; building locally"; build_local; }
fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "==> starting container on http://localhost:$PORT/"
docker run -d --rm --name "$NAME" -p "$PORT:8080" "$IMAGE" >/dev/null

cleanup() { echo; echo "==> stopping"; docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup INT TERM EXIT

# Wait for nginx to answer before opening a browser.
URL="http://localhost:$PORT/"
for _ in $(seq 1 50); do
  if curl -fsS -o /dev/null "$URL" 2>/dev/null; then break; fi
  sleep 0.2
done

if [ "$OPEN" = 1 ]; then
  ( xdg-open "$URL" 2>/dev/null \
    || open "$URL" 2>/dev/null \
    || echo "Open $URL in your browser." ) &
fi

echo "==> Protogon is live at $URL  (Ctrl-C to stop)"
docker logs -f "$NAME"
