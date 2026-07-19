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

FLAGS=(--kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --incognito)

if [ "$(uname -s)" = "Darwin" ]; then
  # macOS: Chrome/Chromium/Edge live in /Applications as .app bundles.
  for app in "Google Chrome" "Chromium" "Microsoft Edge"; do
    BIN="/Applications/$app.app/Contents/MacOS/${app%% *}"
    [ -x "$BIN" ] || BIN="/Applications/$app.app/Contents/MacOS/$app"
    [ -x "$BIN" ] && { exec "$BIN" "${FLAGS[@]}" "$URL"; }
  done
  echo "No Chrome/Chromium/Edge in /Applications. Open $URL manually." >&2; exit 1
fi

BROWSER="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
if [ -z "$BROWSER" ]; then
  echo "No Chromium/Chrome found. Install one, or open $URL manually." >&2
  exit 1
fi
exec "$BROWSER" "${FLAGS[@]}" "$URL"
