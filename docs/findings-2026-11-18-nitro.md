# Nitro 5 (Windows) bring-up, 18 Nov 2026

Machine: Acer Nitro 5 (board out of its case), Windows 11 Pro 10.0.26200, commit 560c8d4
(+ the `backend/cameras.py` fix below). Camera: unidentified — not reported by the OS's
PnP `Camera` class, but OpenCV opens it fine at index 0, 640x480 actual. No external
camera was attached; DroidCam Client (Windows) was installed as a phone-webcam fallback
but not paired — not needed since this camera works.

## Section 1 — Update
- `git pull`: already at `560c8d4`.
- `py -3.11 -m venv .venv` + `pip install -r requirements.txt`: clean; `insightface`
  installed without needing a compiler (no Visual C++ Build Tools were present).
- `npm ci && npm run build`: clean.
- `docker compose up -d db`: `nfc-scan-postgres` healthy on `127.0.0.1:5433`.
- Docker Desktop and DroidCam Client both had to be installed from an already-elevated
  terminal — their installers hung indefinitely waiting for a UAC prompt that never
  rendered when launched from this non-interactive tool session.

## Section 2 — .env
Created from `.env.example`. Non-secret values set: `CAMERA_WIDTH=1280`,
`CAMERA_HEIGHT=720`, `CAMERA_INDEX=0`, `PERCEPTION_ENABLED=true`, `USE_GPU=false`,
`PERCEPTION_STATS_SEC=30`, `NOTIFY_EMAIL_ENABLED=true`, `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, `SMTP_STARTTLS=true`, `NOTIFY_SMS_ENABLED=false`. Left blank for
Cabucos to fill in directly in the file: `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD`,
`SEMAPHORE_API_KEY`, `OPERATOR_TOKEN`.

## Section 3 — Load `.env` and start
- `.env` loaded into the PowerShell process env; backend started with
  `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`.
- Health: `curl.exe -s localhost:8001/health` → `{"status":"ok","db":true}`.
- Dashboard: `GET /app/` → 200 OK, 424 bytes (matches the built `index.html`).
- Serial reader (`python -u -m backend.serial_reader`): starts cleanly, prints
  "no serial port found — waiting for a board" — no crash, since the Arduino/RC522
  isn't connected to this machine yet.

## Section 4 — Tests
- `python -m pytest tests -q` → **497 passed, 11 skipped** — exact match to the Linux
  baseline (18 Nov). No Windows-only failures.
- T1–T10 and liveness calibration (`pilot-macbook.md` sections 4–5): **not run** — they
  need the Arduino + RC522 reader physically attached, which this machine doesn't have
  yet. Everything else in sections 1–4 is verified; T1–T10 are the remaining gate before
  this machine could be used for the pilot.

## Speed
`[perception]` lines, in order:
- `0.0 fps, detection 87908 ms a frame, 2606 camera frames skipped (last 94 s)` — one-time
  stall: first-ever detection call downloads + loads `buffalo_l` (not steady-state).
- `12.7 fps, detection 74 ms a frame, 520 camera frames skipped (last 30 s)`
- `12.9 fps, detection 73 ms a frame, 512 camera frames skipped (last 30 s)`
- `12.4 fps, detection 77 ms a frame, 528 camera frames skipped (last 30 s)`

Well above the 8 fps target, steady across three consecutive windows (~90 s), no growing
lag observed in the window tested. Tap-to-verdict timing (T10) not measured — needs the
physical reader.

## Problems
- **Fixed, needs a passing test run confirmed** (`backend/cameras.py`): `os.uname()`
  crashed on Windows — only macOS and Linux branches existed. Added a `_windows_cameras()`
  path using `Get-PnpDevice -Class Camera -Status OK` (same passive "ask the OS" approach
  as the existing mac/linux code) and branched on `os.name == "nt"` before the
  `os.uname()` call. macOS/Linux code paths are untouched. `pytest tests -q` still
  497 passed / 11 skipped after the change.
- **Not fixed, not blocking**: the new Windows camera check still reports "no cameras
  reported by the OS" even though a real camera is attached and OpenCV opens it fine at
  index 0. The PnP `Camera` device class apparently doesn't cover whatever this camera
  registers as. `pick_index()`'s default-to-0 fallback happens to land on the right
  camera here, so `CAMERA_INDEX=0` was pinned manually in `.env` rather than confirmed via
  `python -m backend.cameras`.
- `backend/ports.py` was checked for the same Windows risk and is fine as-is —
  `pyserial`'s `comports()` and `glob.glob()` both degrade gracefully on Windows.

## Still needed before this machine is pilot-ready
1. Connect the Arduino + RC522 board; confirm `python -m backend.ports` finds it.
2. Run T1–T10 and liveness calibration (`pilot-macbook.md` sections 4–5) with the camera
   and reader both attached.
3. Cabucos to fill in `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD` in `.env` directly, then
   confirm a guardian email actually sends (not yet tested on this machine).
