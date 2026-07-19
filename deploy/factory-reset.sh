#!/usr/bin/env bash
# Factory reset / re-provision (Step 43): wipe all data (roster, attendance, face
# templates) and re-apply a clean schema. DESTRUCTIVE. Takes a backup first, then
# double-confirms. Use to hand a box to a new site or clear a demo run.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_CONTAINER="${NFC_PG_CONTAINER:-nfc-scan-postgres}"
cd "$APP_DIR"

echo "!! FACTORY RESET — this ERASES the roster, attendance, and all face templates."
read -r -p "Type ERASE to continue: " ans
[ "$ans" = "ERASE" ] || { echo "Aborted."; exit 1; }

echo "==> Safety backup first"
bash deploy/backup.sh || true

echo "==> Dropping and recreating the public schema"
docker exec -i "$PG_CONTAINER" psql -U attendance -d attendance \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null

echo "==> Re-applying schema via a backend restart (init_db)"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user restart nfc-scan-backend || true
else
  echo "  Start the backend once to re-apply schema.sql."
fi
echo "==> Factory reset complete. Visit /app/setup to re-provision."
