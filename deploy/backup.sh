#!/usr/bin/env bash
# Backup (Step 43): dump roster + attendance to a timestamped file.
# Restore with deploy/restore.sh. Embeddings ARE included — treat backups as PII.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_CONTAINER="${NFC_PG_CONTAINER:-nfc-scan-postgres}"
OUT_DIR="${NFC_BACKUP_DIR:-$APP_DIR/backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/attendance-$STAMP.sql"

echo "==> Dumping database from container '$PG_CONTAINER' -> $OUT"
docker exec "$PG_CONTAINER" pg_dump -U attendance -d attendance > "$OUT"
echo "==> Backup written ($(du -h "$OUT" | cut -f1)). Keep it somewhere safe — it contains face templates."
