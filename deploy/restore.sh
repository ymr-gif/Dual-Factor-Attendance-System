#!/usr/bin/env bash
# Restore (Step 43): load a backup produced by deploy/backup.sh.
#   deploy/restore.sh backups/attendance-YYYYMMDD-HHMMSS.sql
# Destructive: overwrites current roster + attendance. Prompts first.
set -euo pipefail

FILE="${1:-}"
PG_CONTAINER="${NFC_PG_CONTAINER:-nfc-scan-postgres}"

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "usage: deploy/restore.sh <backup.sql>" >&2; exit 1
fi

read -r -p "This overwrites the current database from '$FILE'. Type YES to proceed: " ans
[ "$ans" = "YES" ] || { echo "Aborted."; exit 1; }

echo "==> Restoring $FILE into container '$PG_CONTAINER'"
cat "$FILE" | docker exec -i "$PG_CONTAINER" psql -U attendance -d attendance >/dev/null
echo "==> Restore complete. Restart the backend if it was running: systemctl --user restart nfc-scan-backend"
