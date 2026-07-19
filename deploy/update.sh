#!/usr/bin/env bash
# Update (Step 43): pull the latest release, migrate, rebuild, restart — data preserved.
# Takes a safety backup first. Schema migration is idempotent (backend applies schema.sql
# on boot via ALTER ... IF NOT EXISTS), so no data loss.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> Safety backup before update"
bash deploy/backup.sh || echo "  (backup skipped — continuing)"

echo "==> Pulling latest code"
git pull --ff-only

if [ -n "${NFC_PYTHON:-}" ]; then PY="$NFC_PYTHON"; elif [ -x "$APP_DIR/.venv/bin/python" ]; then PY="$APP_DIR/.venv/bin/python"; else PY="python3"; fi
echo "==> Updating Python deps"
"$PY" -m pip install -r requirements.txt -q

if command -v npm >/dev/null 2>&1; then
  echo "==> Rebuilding the web UI"
  ( cd frontend && npm ci && npm run build )
fi

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Restarting services (schema self-migrates on boot)"
  systemctl --user restart nfc-scan-backend nfc-scan-reader || true
fi

echo "==> Update complete."
