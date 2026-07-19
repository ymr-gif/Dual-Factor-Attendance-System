#!/usr/bin/env bash
# launchd wrapper (macOS): source .env, then exec the serial reader. Skips cleanly if
# no serial port is configured/present, so the agent doesn't crash-loop without hardware.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"
set -a; [ -f .env ] && . ./.env; set +a
export TAP_URL="${TAP_URL:-http://localhost:${NFC_PORT:-8001}/tap}"
PY="${NFC_PYTHON:-$APP_DIR/.venv/bin/python}"; [ -x "$PY" ] || PY="$(command -v python3)"
exec "$PY" -u -m backend.serial_reader
