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
.avatar-venv/bin/openspline models --directory models --quality low
.avatar-venv/bin/openspline doctor --config avatar-service.yaml
