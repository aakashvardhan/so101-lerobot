#!/usr/bin/env bash
set -euo pipefail

# Hugging Face token from env or mounted secret file
if [ -z "${HF_TOKEN:-}" ] && [ -f /run/secrets/hf_token ]; then
  HF_TOKEN="$(tr -d '[:space:]' < /run/secrets/hf_token)"
  export HF_TOKEN
fi
if [ -n "${HF_TOKEN:-}" ]; then
  export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
fi

# Rerun viewer on host (Docker Desktop: host.docker.internal)
if [ -n "${RERUN_HOST:-}" ]; then
  export RERUN_REMOTE_ADDR="${RERUN_HOST}"
fi

cd /lerobot

if [ "${LEROBOT_SHOW_PORTS:-}" = "1" ]; then
  echo "=== Serial ports (lerobot-find-port) ==="
  lerobot-find-port 2>/dev/null || true
  echo "=== Set ROBOT_PORT / LEADER_PORT in .env (Linux: /dev/ttyACM*) ==="
fi

exec "$@"
