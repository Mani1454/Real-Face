#!/usr/bin/env bash
# Start the local voice app and GPU renderer, reusing healthy running services.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p .avatar-runtime
owned_pids=()
cleanup() {
  for process_id in "${owned_pids[@]}"; do
    kill "$process_id" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if ! curl -fsS --max-time 2 http://127.0.0.1:7860/healthz >/dev/null 2>&1; then
  if [[ ! -s models/avatar/Model_Lite/diffusion_pytorch_model.safetensors || ! -s models/avatar/VAE_LTX/diffusion_pytorch_model.safetensors ]] || \
    [[ ! -s models/audio/model.safetensors && ! -s models/audio/pytorch_model.bin ]]; then
    echo 'Finish model setup first: bash scripts/setup_avatar.sh'
    exit 1
  fi
  bash scripts/start_avatar.sh >.avatar-runtime/local-renderer.log 2>&1 &
  owned_pids+=("$!")
  echo 'Starting GPU renderer. Logs: .avatar-runtime/local-renderer.log'
fi

if ! curl -fsS --max-time 2 http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  if [[ ! -x .venv/bin/uvicorn ]]; then
    echo 'Install the voice app dependencies first, following README.md.'
    exit 1
  fi
  .venv/bin/uvicorn server:app --app-dir code --host 127.0.0.1 --port 8000 >.avatar-runtime/local-voice.log 2>&1 &
  owned_pids+=("$!")
fi

echo 'Waiting for the GPU model to load…'
ready=false
for ((attempt=0; attempt<300; attempt++)); do
  if curl -fsS --max-time 2 http://127.0.0.1:7860/readyz >/dev/null 2>&1; then
    ready=true
    break
  fi
  for process_id in "${owned_pids[@]}"; do
    if ! kill -0 "$process_id" 2>/dev/null; then
      echo 'A service stopped. Check .avatar-runtime/local-renderer.log and local-voice.log.'
      exit 1
    fi
  done
  sleep 2
done
if [[ "$ready" != true ]]; then
  echo 'Renderer startup timed out. Check .avatar-runtime/local-renderer.log.'
  exit 1
fi
echo 'Ready: http://localhost:8000 — the face connects automatically. Choose Start conversation to talk.'
if ((${#owned_pids[@]})); then
  echo 'Leave this terminal open. Ctrl+C stops only the services started here.'
  wait "${owned_pids[@]}"
fi
