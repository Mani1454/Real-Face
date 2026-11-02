#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
command -v ffmpeg >/dev/null || { echo 'Install FFmpeg first.'; exit 1; }
command -v nvidia-smi >/dev/null || { echo 'A supported NVIDIA GPU and driver are required.'; exit 1; }
# Pin the reviewed service source, including its GPU dependency constraints.
if [[ ! -x .avatar-venv/bin/python ]]; then
  uv venv --python 3.12 .avatar-venv
fi
uv pip install --python .avatar-venv/bin/python \
  'openspline-server[gpu] @ git+https://github.com/openspline/openspline.git@1e5f2b06e6c3dfc68e59ab9bfb3b30997d51caf9#subdirectory=packages/server' \
  --torch-backend cu126
download_ready=false
for download_attempt in 1 2 3; do
  if HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}" HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-45}" \
    .avatar-venv/bin/openspline models --directory models --quality low; then
    download_ready=true
    break
  fi
  if [[ "$download_attempt" != 3 ]]; then
    echo 'Model download interrupted. Resuming saved progress in 5 seconds…'
    sleep 5
  fi
done
if [[ "$download_ready" != true ]]; then
  echo 'Model download is incomplete. Rerun this script to resume.'
  exit 1
fi
.avatar-venv/bin/openspline doctor --config avatar-service.yaml
