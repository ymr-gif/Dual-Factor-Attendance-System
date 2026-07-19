#!/usr/bin/env bash
# Appliance provisioning (Step 40) — fresh Linux box -> one command -> running guardpost.
#
#   Postgres (docker) + Python deps + liveness models + built SPA + systemd services.
#   Idempotent: safe to re-run. GPU/camera/serial are optional (see preflight).
#
# Env overrides:
#   NFC_PYTHON=/path/to/python   reuse an existing interpreter instead of a fresh .venv
#   NFC_PORT=8001                backend port (default 8001)
#   NFC_DB_PORT=5433             host port for the Postgres container (default 5433)
#   NFC_NO_SYSTEMD=1             skip installing/starting systemd user units
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${NFC_PORT:-8001}"
DB_PORT="${NFC_DB_PORT:-5433}"
PG_CONTAINER="nfc-scan-postgres"
PG_VOLUME="nfc-scan-pgdata"

say(){ printf '\n\033[36m==>\033[0m %s\n' "$1"; }

cd "$APP_DIR"
say "Provisioning nfc-scan (Dual-Factor Attendance) in $APP_DIR"

# 1) Preflight (warn-only)
bash deploy/preflight.sh || true

# 2) .env
if [ ! -f .env ]; then
  say "Writing .env from .env.example"
  cp .env.example .env
  command -v nvidia-smi >/dev/null 2>&1 && sed -i 's/^USE_GPU=.*/USE_GPU=true/' .env 2>/dev/null || true
else
  say ".env already exists — leaving it untouched"
fi

# 3) Python environment
if [ -n "${NFC_PYTHON:-}" ]; then
  PY="$NFC_PYTHON"
  say "Reusing interpreter: $PY"
else
  if [ ! -d .venv ]; then
    say "Creating virtualenv (.venv) + installing requirements (this pulls a large CV tree)"
    python3 -m venv .venv
  fi
  PY="$APP_DIR/.venv/bin/python"
  "$PY" -m pip install --upgrade pip -q
  "$PY" -m pip install -r requirements.txt -q
fi

# 4) Postgres (docker container, persistent volume)
if command -v docker >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
      say "Starting existing Postgres container"
      docker start "$PG_CONTAINER"
    else
      say "Creating Postgres container ($PG_CONTAINER) on port $DB_PORT with a persistent volume"
      docker run -d --name "$PG_CONTAINER" --restart unless-stopped \
        -p "${DB_PORT}:5432" -v "${PG_VOLUME}:/var/lib/postgresql/data" \
        -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
        pgvector/pgvector:pg16
    fi
  else
    say "Postgres container already running"
  fi
else
  say "!! docker not found — provide a Postgres 16 + pgvector yourself and set DB_DSN in .env"
fi

# 5) Liveness models (idempotent fetch)
say "Fetching liveness (anti-spoof) models"
"$PY" -m backend.fetch_liveness_models || echo "  (model fetch skipped/failed — liveness will fail-open)"

# 6) Build the SPA
if command -v npm >/dev/null 2>&1; then
  say "Building the web UI"
  ( cd frontend && npm ci && npm run build )
else
  say "!! npm not found — skipping SPA build (backend still serves the API)"
fi

# 7) systemd user services
if [ "${NFC_NO_SYSTEMD:-0}" != "1" ] && command -v systemctl >/dev/null 2>&1; then
  say "Installing systemd user services"
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  for unit in nfc-scan-backend nfc-scan-reader; do
    sed -e "s#__APP_DIR__#${APP_DIR}#g" -e "s#__PY__#${PY}#g" \
      "deploy/systemd/${unit}.service" > "${UNIT_DIR}/${unit}.service"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now nfc-scan-backend nfc-scan-reader
  # Boot without an interactive login (best-effort; needs sudo).
  loginctl enable-linger "$USER" 2>/dev/null || echo "  (run: sudo loginctl enable-linger $USER  — for start-at-boot)"
else
  say "Skipping systemd (NFC_NO_SYSTEMD=1 or systemctl absent). Run manually:"
  echo "  $PY -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
fi

say "Done. Open  http://localhost:${PORT}/app/setup  to finish setup in the browser."
echo "   Kiosk auto-start: see deploy/kiosk/README.md"
