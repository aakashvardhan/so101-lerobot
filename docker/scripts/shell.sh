#!/usr/bin/env bash
# Interactive dev shell (CPU image)
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose run --rm lerobot "$@"
