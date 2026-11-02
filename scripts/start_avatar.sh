#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .avatar-venv/bin/openspline ]]; then
  echo 'Run bash scripts/setup_avatar.sh first.'
  exit 1
fi
exec .avatar-venv/bin/python scripts/serve_avatar.py
