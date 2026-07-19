#!/usr/bin/env bash
# launchd wrapper (macOS): source .env (launchd has no EnvironmentFile), then exec
# the backend. Self-locating so the plist only needs an absolute path to this file.
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"
set -a; [ -f .env ] && . ./.env; set +a
export PERCEPTION_ENABLED="${PERCEPTION_ENABLED:-true}"
PY="${NFC_PYTHON:-$APP_DIR/.venv/bin/python}"; [ -x "$PY" ] || PY="$(command -v python3)"
exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "${NFC_PORT:-8001}"
