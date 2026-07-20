#!/usr/bin/env bash
# Preflight (Step 40): report what the appliance needs. Warn-only — never fails the
# install. Cross-platform: Debian/Ubuntu (systemd, /dev/videoN, /dev/ttyACM0) and
# macOS (launchd, AVFoundation camera, /dev/cu.usbmodem*).
set -uo pipefail

OS="$(uname -s)"
ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$1"; }
bad(){  printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo "== nfc-scan preflight ($OS) =="

command -v docker  >/dev/null 2>&1 && ok "docker present" || bad "docker missing (needed for Postgres; use Docker Desktop on macOS)"
command -v node    >/dev/null 2>&1 && ok "node present ($(node -v 2>/dev/null))" || warn "node missing (needed to build the SPA)"
if command -v python3 >/dev/null 2>&1; then
  pv="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
  case "$pv" in
    3.10|3.11|3.12) ok "python3 present ($(python3 -V 2>&1))";;
    *) warn "python3 is $pv — onnxruntime needs 3.10–3.12; installer will use python3.11 if present (brew install python@3.11)";;
  esac
else bad "python3 missing"; fi

if command -v nvidia-smi >/dev/null 2>&1; then
  ok "NVIDIA GPU detected — set USE_GPU=true for ~5-10x on recognition"
else
  [ "$OS" = "Darwin" ] && warn "no NVIDIA GPU (Macs have none) — runs on CPU; keep USE_GPU=false" \
                        || warn "no NVIDIA GPU (nvidia-smi absent) — runs on CPU (fine for a demo)"
fi

if [ "$OS" = "Darwin" ]; then
  xcode-select -p >/dev/null 2>&1 && ok "Xcode command-line tools present" || warn "Xcode CLT missing (insightface build): xcode-select --install"
  system_profiler SPCameraDataType 2>/dev/null | grep -q ':' && ok "camera detected (AVFoundation)" || warn "no camera detected — perception idles until a webcam is present"
  macport="$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)"
  [ -n "$macport" ] && ok "serial reader at $macport" || warn "no /dev/cu.usbmodem* (Arduino) — set SERIAL_PORT in .env, or POST /tap to demo"
else
  ls /dev/video0 >/dev/null 2>&1 && ok "camera at /dev/video0" || warn "no /dev/video0 (perception idles until a webcam is present)"
  [ -e /dev/ttyACM0 ] && ok "serial reader at /dev/ttyACM0" || warn "no /dev/ttyACM0 (Arduino) — set SERIAL_PORT in .env, or POST /tap to demo"
  id -nG "$USER" | grep -qw video   && ok "user in 'video' group"   || warn "not in 'video' group (webcam): sudo usermod -aG video $USER"
  id -nG "$USER" | grep -qw dialout && ok "user in 'dialout' group" || warn "not in 'dialout' group (serial): sudo usermod -aG dialout $USER"
fi

echo "== preflight done (warnings are OK for a prototype) =="
