#!/usr/bin/env bash
# Preflight (Step 40): report what the appliance needs. Warn-only — never fails the
# install, so you can provision on a dev box now and plug in GPU/camera/reader later.
set -uo pipefail

ok(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$1"; }
bad(){ printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo "== nfc-scan preflight =="

command -v docker >/dev/null 2>&1 && ok "docker present" || bad "docker missing (needed for Postgres)"
command -v node   >/dev/null 2>&1 && ok "node present ($(node -v 2>/dev/null))" || warn "node missing (needed to build the SPA)"
command -v python3 >/dev/null 2>&1 && ok "python3 present ($(python3 -V 2>&1))" || bad "python3 missing"

if command -v nvidia-smi >/dev/null 2>&1; then
  ok "NVIDIA GPU detected — set USE_GPU=true for ~5-10x on recognition"
else
  warn "no NVIDIA GPU (nvidia-smi absent) — runs on CPU (fine for a demo)"
fi

if [ -e /dev/video0 ]; then ok "camera at /dev/video0"; else warn "no /dev/video0 (perception will idle until a webcam is present)"; fi
if [ -e /dev/ttyACM0 ]; then ok "serial reader at /dev/ttyACM0"; else warn "no /dev/ttyACM0 (Arduino reader) — you can POST /tap manually to demo"; fi

id -nG "$USER" | grep -qw video && ok "user in 'video' group" || warn "user not in 'video' group (webcam access): sudo usermod -aG video $USER"
id -nG "$USER" | grep -qw dialout && ok "user in 'dialout' group" || warn "user not in 'dialout' group (serial access): sudo usermod -aG dialout $USER"

echo "== preflight done (warnings are OK for a prototype) =="
