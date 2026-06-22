#!/usr/bin/env bash
#
# Render the Protogon turntable loop on a remote NVIDIA GPU box using Cycles +
# OptiX, then pull the finished poster / MP4 / GIF / contact-sheet back into the
# repo. This is the "accurate renders, fast" path: path tracing runs on the GPU.
#
# Usage:
#   tools/render-on-roy.sh [HOST]            # HOST defaults to roy.wye.it
#
# Optional env knobs:
#   SAMPLES     Cycles samples           (default 128)
#   WIDTH       frame width  in px       (default 1280)
#   HEIGHT      frame height in px       (default 720)
#   FRAMES      loop length  in frames   (default 96)
#   ENGINE      render engine            (default cycles)
#   REMOTE_DIR  remote repo dir name     (default codemyriad-protogon-work)
#
# Requirements on HOST: ssh access, Blender >= 4.2 and ffmpeg on PATH, an NVIDIA
# GPU (OptiX). Run this script from anywhere inside the repo.
#
# NOTE: this OVERWRITES codemyriad-protogon/renders/blender/ with fresh output.
set -euo pipefail

HOST="${1:-roy.wye.it}"
REMOTE_DIR="${REMOTE_DIR:-codemyriad-protogon-work}"
ENGINE="${ENGINE:-cycles}"
SAMPLES="${SAMPLES:-128}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FRAMES="${FRAMES:-192}"

# Resolve repo root = parent of this script's tools/ directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ">> [1/3] syncing repo to ${HOST}:${REMOTE_DIR}/ ..."
rsync -az --info=stats1 \
  --exclude='_upstream_badge_2024_hardware/' \
  --exclude='__pycache__/' \
  --exclude='*.log' \
  ./ "${HOST}:${REMOTE_DIR}/"

echo ">> [2/3] rendering on ${HOST} GPU (${ENGINE}, ${WIDTH}x${HEIGHT}, ${SAMPLES} spp, ${FRAMES} frames) ..."
# Render the REAL board geometry (copper/pads/silk/mask/holes) from the GLB with
# lit PCB materials -- NOT the old flat emissive decal planes (which faked the
# detail, mis-oriented the back face, and squared off a hexagon corner). To fall
# back to the decal art, re-add --top-texture/--bottom-texture here.
ssh "$HOST" "cd ~/${REMOTE_DIR}/codemyriad-protogon && blender -b -P ../tools/render_protogon_blender.py -- \
  --engine ${ENGINE} --samples ${SAMPLES} --width ${WIDTH} --height ${HEIGHT} --frames ${FRAMES} \
  --model renders/model/codemyriad-protogon.glb \
  --outdir renders/blender"

echo ">> [3/3] pulling rendered outputs back into the repo ..."
rsync -az "${HOST}:${REMOTE_DIR}/codemyriad-protogon/renders/blender/" \
  codemyriad-protogon/renders/blender/

echo ">> done. Updated deliverables in codemyriad-protogon/renders/blender/:"
ls -la codemyriad-protogon/renders/blender/
