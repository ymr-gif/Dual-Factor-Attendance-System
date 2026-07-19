#!/usr/bin/env bash
# Appliance provisioning (Step 40) — fresh box -> one command -> running guardpost.
# Cross-platform: Debian/Ubuntu (systemd) and macOS (launchd). Same app, same steps;
# only the auto-start mechanism and a couple of device paths differ.
#
#   Postgres (docker) + Python deps + liveness models + built SPA + auto-start services.
#   Idempotent. GPU/camera/serial are optional (see preflight).
#
# Env overrides:
#   NFC_PYTHON=/path/to/python   reuse an interpreter instead of a fresh .venv
#   NFC_PORT=8001                backend port (default 8001)
#   NFC_DB_PORT=5433             host port for the Postgres container (default 5433)
#   NFC_NO_AUTOSTART=1           skip installing/starting systemd/launchd services
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"                       # Linux | Darwin
PORT="${NFC_PORT:-8001}"
DB_PORT="${NFC_DB_PORT:-5433}"
PG_CONTAINER="nfc-scan-postgres"
PG_VOLUME="nfc-scan-pgdata"

say(){ printf '\n\033[36m==>\033[0m %s\n' "$1"; }

cd "$APP_DIR"
say "Provisioning nfc-scan (Dual-Factor Attendance) on $OS in $APP_DIR"

# 1) Preflight (warn-only)
bash deploy/preflight.sh || true

# 2) .env  (+ macOS serial auto-detect: Arduino shows up as /dev/cu.usbmodem*)
if [ ! -f .env ]; then
  say "Writing .env from .env.example"
  cp .env.example .env
  if command -v nvidia-smi >/dev/null 2>&1; then sed -i.bak 's/^USE_GPU=.*/USE_GPU=true/' .env && rm -f .env.bak; fi
  if [ "$OS" = "Darwin" ]; then
    macport="$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)"
    [ -n "$macport" ] && { echo "SERIAL_PORT=$macport" >> .env; say "Detected Arduino at $macport (written to .env)"; }
  fi
else
  say ".env already exists — leaving it untouched"
fi

# 3) Python environment
if [ -n "${NFC_PYTHON:-}" ]; then
  PY="$NFC_PYTHON"; say "Reusing interpreter: $PY"
else
  BASE_PY="python3"; command -v python3.11 >/dev/null 2>&1 && BASE_PY="python3.11"
  if [ ! -d .venv ]; then say "Creating virtualenv (.venv) with $BASE_PY"; "$BASE_PY" -m venv .venv; fi
  PY="$APP_DIR/.venv/bin/python"
  say "Installing Python requirements (pulls a large CV tree; on macOS needs Xcode CLT: xcode-select --install)"
  "$PY" -m pip install --upgrade pip -q
  "$PY" -m pip install -r requirements.txt -q
fi

# 4) Postgres (docker container, persistent volume) — Docker Desktop on macOS
if command -v docker >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
      say "Starting existing Postgres container"; docker start "$PG_CONTAINER"
    else
      say "Creating Postgres container ($PG_CONTAINER) on port $DB_PORT with a persistent volume"
      docker run -d --name "$PG_CONTAINER" --restart unless-stopped \
        -p "${DB_PORT}:5432" -v "${PG_VOLUME}:/var/lib/postgresql/data" \
        -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
        pgvector/pgvector:pg16
    fi
  else say "Postgres container already running"; fi
else
  say "!! docker not found — install Docker (Desktop on macOS), or set DB_DSN in .env to your own Postgres 16 + pgvector"
fi

# 5) Liveness models (idempotent)
say "Fetching liveness (anti-spoof) models"
"$PY" -m backend.fetch_liveness_models || echo "  (model fetch skipped/failed — liveness will fail-open)"

# 6) Build the SPA
if command -v npm >/dev/null 2>&1; then
  say "Building the web UI"; ( cd frontend && npm ci && npm run build )
else
  say "!! npm not found — skipping SPA build (install Node; backend still serves the API)"
fi

# 7) Auto-start service
if [ "${NFC_NO_AUTOSTART:-0}" = "1" ]; then
  say "Skipping auto-start (NFC_NO_AUTOSTART=1). Run manually:"
  echo "  $PY -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
elif [ "$OS" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  say "Installing systemd user services"
  UNIT_DIR="$HOME/.config/systemd/user"; mkdir -p "$UNIT_DIR"
  for unit in nfc-scan-backend nfc-scan-reader; do
    sed -e "s#__APP_DIR__#${APP_DIR}#g" -e "s#__PY__#${PY}#g" \
      "deploy/systemd/${unit}.service" > "${UNIT_DIR}/${unit}.service"
  done
  systemctl --user daemon-reload
  systemctl --user enable --now nfc-scan-backend nfc-scan-reader
  loginctl enable-linger "$USER" 2>/dev/null || echo "  (run: sudo loginctl enable-linger $USER  — for start-at-boot)"
elif [ "$OS" = "Darwin" ]; then
  say "Installing launchd agents (macOS auto-start)"
  LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
  export NFC_PYTHON="$PY"   # the run-*.sh wrappers pick this up; persist for launchd via .env
  grep -q '^NFC_PYTHON=' .env 2>/dev/null || echo "NFC_PYTHON=$PY" >> .env
  for a in backend reader; do
    sed "s#__APP_DIR__#${APP_DIR}#g" "deploy/launchd/com.nfc-scan.${a}.plist" > "$LA/com.nfc-scan.${a}.plist"
    launchctl unload "$LA/com.nfc-scan.${a}.plist" 2>/dev/null || true
    launchctl load "$LA/com.nfc-scan.${a}.plist"
  done
  echo "  Grant Camera + (if used) Serial access to the terminal/uvicorn when macOS prompts."
else
  say "No systemd/launchd — run manually:"; echo "  $PY -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
fi

say "Done. Open  http://localhost:${PORT}/app/setup  to finish setup in the browser."
echo "   Kiosk auto-start: see deploy/kiosk/README.md (Linux) — on macOS run deploy/kiosk/start-kiosk.sh"
