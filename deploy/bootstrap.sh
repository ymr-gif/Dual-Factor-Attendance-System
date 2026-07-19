#!/usr/bin/env bash
# Downloadable "button" (Step 41): one command on a fresh box.
#
#   curl -fsSL https://raw.githubusercontent.com/ymr-gif/Dual-Factor-Attendance-System/main/deploy/bootstrap.sh | bash
#
# Clones the repo (or updates it) and runs the appliance installer. For a real
# GitHub Release you'd attach a self-extracting .run wrapping this — for the
# prototype, curl|bash is the button.
set -euo pipefail

REPO="${NFC_REPO:-https://github.com/ymr-gif/Dual-Factor-Attendance-System.git}"
DEST="${NFC_DEST:-$HOME/nfc-scan}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required. Install it and re-run." >&2; exit 1
fi

if [ -d "$DEST/.git" ]; then
  echo "==> Updating existing checkout in $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "==> Cloning $REPO -> $DEST"
  git clone "$REPO" "$DEST"
fi

cd "$DEST"
exec bash deploy/install.sh
