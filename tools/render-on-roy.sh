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
#   FRAMES      loop length  in frames   (default 192)
#   ENGINE      render engine            (default cycles)
#   XRAY        set to 1 for the translucent-soldermask routing view (default off)
#   OUTSUB      output subdir under renders/ (default blender; e.g. blender-xray)
#   REMOTE_DIR  remote repo dir name     (default codemyriad-protogon-work)
#
# Examples:
#   tools/render-on-roy.sh                                  # product loop
#   XRAY=1 OUTSUB=blender-xray tools/render-on-roy.sh       # X-ray routing loop
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
OUTSUB="${OUTSUB:-blender}"
xray_flag=""; [ -n "${XRAY:-}" ] && xray_flag="--xray"

# Resolve repo root = parent of this script's tools/ directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ">> [1/3] syncing repo to ${HOST}:${REMOTE_DIR}/ ..."
rsync -az --info=stats1 \
  --exclude='_upstream_badge_2024_hardware/' \
  --exclude='__pycache__/' \
  --exclude='*.log' \
  ./ "${HOST}:${REMOTE_DIR}/"

echo ">> [2/3] rendering on ${HOST} GPU (${ENGINE}, ${WIDTH}x${HEIGHT}, ${SAMPLES} spp, ${FRAMES} frames${xray_flag:+, XRAY}) -> renders/${OUTSUB} ..."
# Renders the real board geometry (copper/pads/silk/mask/holes) from the GLB with lit
# PCB materials, an HDRI studio environment, and the EMF-sign photo backdrop.
ssh "$HOST" "cd ~/${REMOTE_DIR}/codemyriad-protogon && blender -b -P ../tools/render_protogon_blender.py -- \
  --engine ${ENGINE} --samples ${SAMPLES} --width ${WIDTH} --height ${HEIGHT} --frames ${FRAMES} ${xray_flag} \
  --model renders/model/codemyriad-protogon.glb \
  --outdir renders/${OUTSUB}"

echo ">> [3/3] pulling rendered outputs back into the repo ..."
mkdir -p "codemyriad-protogon/renders/${OUTSUB}"
rsync -az "${HOST}:${REMOTE_DIR}/codemyriad-protogon/renders/${OUTSUB}/" \
  "codemyriad-protogon/renders/${OUTSUB}/"

echo ">> done. Updated deliverables in codemyriad-protogon/renders/${OUTSUB}/:"
ls -la "codemyriad-protogon/renders/${OUTSUB}/"
