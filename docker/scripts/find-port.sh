#!/usr/bin/env bash
# List serial ports visible inside the container
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose run --rm -e LEROBOT_SHOW_PORTS=1 lerobot lerobot-find-port "$@"
