#!/usr/bin/env bash
# Run uv sync then fix macOS-hidden .pth files (see scripts/fix_editable_venv.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
uv sync "$@"
python3 scripts/fix_editable_venv.py
