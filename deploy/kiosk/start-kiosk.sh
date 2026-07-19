#!/usr/bin/env bash
# Kiosk launcher (Step 40): full-screen the guardpost UI on boot. Waits for the
# backend, then opens Chromium in kiosk mode at the public Viewer (boxes-only, no PII).
# Point KIOSK_URL at /app/ (operator) or /app/kiosk for the verdict screen instead.
set -uo pipefail

URL="${KIOSK_URL:-http://localhost:8001/app/viewer}"

# Wait for the backend to answer (up to ~60s).
for _ in $(seq 1 60); do
  curl -fsS "http://localhost:8001/health" >/dev/null 2>&1 && break
  sleep 1
done

BROWSER="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
if [ -z "$BROWSER" ]; then
  echo "No Chromium/Chrome found. Install one, or open $URL manually." >&2
  exit 1
fi

exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars \
  --disable-session-crashed-bubble --incognito "$URL"
