# Deploy — appliance provisioning & operations (Steps 40–43)

> **Prototype / MVP.** This gets the app onto a Linux box and running as an auto-start
> appliance for a **demo**. It is **not** production-hardened — see the security/legal
> notes in the root `README.md` before any real deployment with student data.

## One-command install (Steps 40–41)

Fresh box, from the internet — the "button":

```bash
curl -fsSL https://raw.githubusercontent.com/ymr-gif/Dual-Factor-Attendance-System/main/deploy/bootstrap.sh | bash
```

Or from a checkout:

```bash
bash deploy/install.sh
```

What it does (idempotent, safe to re-run):
1. `deploy/preflight.sh` — checks GPU / camera `/dev/video0` / serial `/dev/ttyACM0` / docker / node (warn-only).
2. Writes `.env` from `.env.example` (sets `USE_GPU=true` if an NVIDIA GPU is present).
3. Python deps — reuses `$NFC_PYTHON` if set, else builds a `.venv`.
4. Postgres 16 + pgvector as a docker container (`nfc-scan-postgres`, port 5433, persistent volume).
5. Fetches the liveness (anti-spoof) models.
6. Builds the SPA (`frontend/`).
7. Installs + enables the systemd **user** services (backend + reader) and `enable-linger` for start-at-boot.

Then open **`http://localhost:8001/app/setup`** and finish in the browser (Step 42 — no terminal).

Useful overrides: `NFC_PYTHON=/path/to/python`, `NFC_PORT`, `NFC_DB_PORT`, `NFC_NO_AUTOSTART=1`.

**macOS** is fully supported by the same installer — it uses **launchd** agents
(`deploy/launchd/`) instead of systemd, auto-detects the Arduino at `/dev/cu.usbmodem*`, and runs
on CPU (no CUDA). Prereqs: `xcode-select --install`, `brew install python@3.11 node`, Docker Desktop.
See the **Running on macOS** section in the root `README.md` for the full walkthrough.

## Kiosk auto-start (Step 40)

Full-screen the UI on login:

```bash
cp deploy/kiosk/nfc-scan-kiosk.desktop ~/.config/autostart/
# edit the Exec path if the repo isn't at ~/dev/python-projects/nfc-scan
```

`deploy/kiosk/start-kiosk.sh` waits for the backend, then opens Chromium `--kiosk` at the
public **Viewer** (boxes only, no PII). Set `KIOSK_URL=http://localhost:8001/app/kiosk` for the
verdict screen, or `/app/` for the operator dashboard.

## Updates, backup & recovery (Step 43)

```bash
bash deploy/backup.sh                       # -> backups/attendance-<ts>.sql  (contains face templates — treat as PII)
bash deploy/restore.sh backups/<file>.sql   # overwrite DB from a backup (confirms first)
bash deploy/update.sh                        # backup -> git pull -> deps -> rebuild -> restart (schema self-migrates; data kept)
bash deploy/factory-reset.sh                 # wipe all data + re-apply clean schema (double-confirm; backs up first)
```

Makefile shortcuts: `make appliance`, `make backup`, `make restore FILE=…`, `make update`.

## Services

```bash
systemctl --user status  nfc-scan-backend nfc-scan-reader
systemctl --user restart nfc-scan-backend
journalctl --user -u nfc-scan-backend -f
```

A graceful restart can hang in `deactivating` while a dashboard WebSocket / `/stream.mjpeg`
drains — if so: `systemctl --user kill -s SIGKILL nfc-scan-backend && systemctl --user start nfc-scan-backend`.

## Deferred to the real RTX 1050 box

Live NVIDIA driver + CUDA/cuDNN + `onnxruntime-gpu`, kiosk auto-login, and camera/serial on
real hardware. The installer is built and runnable in a VM/container up to those device steps.
Windows (Inno Setup `.exe`) is a documented alternative, not built here.
