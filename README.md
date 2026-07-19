# Dual-Factor Attendance System (nfc-scan)

Guardpost attendance for a school kiosk: an **NFC card (RC522)** identifies the student and a
**face check** confirms it's really them — two factors against cloned/shared cards. A continuous
perception pipeline correlates taps with faces in real time (tap-then-face or face-then-tap),
with passive liveness, a live operator dashboard, kiosk verdict screen, and a boxes-only public
viewer.

> ⚠️ **Prototype / research build — NOT production-ready.** This is an MVP that demonstrates the
> full process end-to-end. It handles children's biometrics, which is special-category data: a real
> deployment requires guardian consent + a DPIA, encryption at rest, access-control hardening, and
> liveness calibration — **none of which are complete here.** See "Not production-ready" below and
> [`docs/design-notes.md`](docs/design-notes.md). The bundled InsightFace `buffalo_l` model is
> **non-commercial research only** ([`NOTICE`](NOTICE)) — obtain rights before any commercial use.

## Quickstart

**One command** — same installer runs on **Debian/Ubuntu (systemd)** and **macOS (launchd)**. It
installs Postgres+pgvector, Python deps, models, builds the UI, and installs auto-start services:

```bash
curl -fsSL https://raw.githubusercontent.com/ymr-gif/Dual-Factor-Attendance-System/main/deploy/bootstrap.sh | bash
# then open http://localhost:8001/app/setup  and finish in the browser (no terminal)
```

From a checkout: `make appliance` (or `bash deploy/install.sh`). Dev loop: `make dev` + `make web-dev`.
Full deploy / backup / update docs: [`deploy/README.md`](deploy/README.md). macOS specifics below.

## Running on macOS

The **same project** runs on a Mac (Intel or Apple Silicon) — identical backend, DB, UI, face +
liveness. Only three things differ from Linux, and the installer handles them:

- **Auto-start** uses **launchd** (`~/Library/LaunchAgents/com.nfc-scan.*`), not systemd.
- **No CUDA on Macs** — inference runs on **CPU** (keep `USE_GPU=false`; it's slower but fine for a demo).
- **Device paths** — the Arduino is `/dev/cu.usbmodem*` (auto-detected into `.env`), and the camera
  comes from AVFoundation via `CAMERA_INDEX` (default 0) — there's no `/dev/video0`.

**Prerequisites** (one time):

```bash
xcode-select --install                      # build tools (needed for insightface)
brew install python@3.11 node
# install Docker Desktop from https://www.docker.com/products/docker-desktop and launch it
```

**Install (one command, same as Linux):**

```bash
curl -fsSL https://raw.githubusercontent.com/ymr-gif/Dual-Factor-Attendance-System/main/deploy/bootstrap.sh | bash
# or, from a checkout:  make appliance
```

This creates a `.venv`, starts the Postgres container, fetches models, builds the SPA, and loads the
launchd agents (backend + reader) so they start on login. Then open
**`http://localhost:8001/app/setup`**. macOS will prompt for **Camera** access the first time — allow it.

**Manual run** (no auto-start, e.g. for a quick demo):

```bash
NFC_NO_AUTOSTART=1 make appliance                 # provision only, no launchd
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

**NFC reader:** `ls /dev/cu.*` to find the Arduino, set `SERIAL_PORT=/dev/cu.usbmodemXXXX` in `.env`,
then `python -m backend.serial_reader`. **No hardware?** Simulate a tap:

```bash
curl -X POST localhost:8001/tap -H 'Content-Type: application/json' -d '{"uid":"CCF98E02"}'
```

**launchd controls:** `launchctl list | grep nfc-scan` ·
`launchctl unload ~/Library/LaunchAgents/com.nfc-scan.backend.plist` (stop) · logs in
`backend.launchd.log` / `reader.launchd.log`. Backup/update scripts (`deploy/*.sh`) work unchanged.

## Docs map

- **[`ROADMAP.md`](ROADMAP.md)** — the plan (five tracks, dependency-ordered build sequence).
- **[`docs/build-log.md`](docs/build-log.md)** — what each built step actually contains.
- **[`docs/design-notes.md`](docs/design-notes.md)** — constraints, failure modes, legal/ethical gates.
- **[`deploy/README.md`](deploy/README.md)** — appliance install, kiosk, backup/update (Steps 40–43).
- Runbooks: [`docs/verification.md`](docs/verification.md), [`docs/face-verification.md`](docs/face-verification.md), [`docs/privacy.md`](docs/privacy.md).

## Not production-ready (before any real deployment)

- **Legal:** guardian consent gate exists but is **off by default**; no DPIA; `buffalo_l` is non-commercial.
- **Security:** `OPERATOR_TOKEN` unset = open API by default; no per-user roles; **no encryption at rest** for face templates; CORS not locked down.
- **Unverified:** liveness threshold **not calibrated** (spoof detection advisory only); SMTP not tested against a live provider; GPU throughput not validated on the target box.

## Structure

- `arduino/nfc_scan/` — Arduino sketch, RC522 UID read, relay only (no on-device auth decision)
- `backend/` — FastAPI + Postgres logging service

## Architecture (locked)

- Arduino → UID over serial → laptop (relay only, no whitelist/decision on-device)
- FastAPI backend (`backend/main.py`)
- Postgres: `students` (uid → identity, `face_embedding`) + `attendance_logs` (student_id, timestamp, method, liveness_score, face_score, face_match)
- SMTP: guardian notify (currently a print stub, see `backend/notify.py`)
- InsightFace `buffalo_l` (ArcFace, 512-d): 1:1 match — NFC identifies, face verifies (built, Step 6). Chosen over `face_recognition`/dlib: no compile, better on off-angle/uneven-light faces.
- MiniFASNet (Silent-Face-Anti-Spoofing): passive liveness (built, Step 7 — `backend/liveness.py`, fail-open; ⚠ threshold not yet calibrated live)

Rule: no face/liveness work starts until tap → log → notify runs end-to-end. That milestone is done (see Status).

## Hardware

RC522 → Arduino Uno

| RC522 | Uno |
|-------|-----|
| SDA   | 10  |
| SCK   | 13  |
| MOSI  | 11  |
| MISO  | 12  |
| RST   | 9   |
| GND   | GND |
| 3.3V  | 3.3V |

USB webcam on the backend laptop (face verification). Selected via `CAMERA_INDEX` (default 0). Subjects: children at a controlled kiosk (they stop and face the camera).

## Face verification (Step 6)

NFC identifies the student; the face check confirms it's really them (2nd factor vs cloned cards). Built and verified live (see [`docs/face-verification.md`](docs/face-verification.md) for the full runbook). **Fail-open**: no camera / no face / no enrolled reference → attendance still logs, scores stay NULL, notify prints a warning.

- Library: InsightFace `buffalo_l` (ArcFace, 512-d), CPU. Model auto-downloads once to `~/.insightface`.
- Face is stored as a **512-d embedding** in `students.face_embedding` (pgvector) — no photo is kept on disk.

- CPU-tuned: recognition runs once on the largest face, so tap cost (~0.7s) is independent of crowd size. `USE_GPU=true` moves both face + liveness onto CUDA (auto-fallback to CPU) — flip it on after migrating to the RTX 1050 box, no code change.

```
python -m backend.enroll S001 --images a.jpg b.jpg c.jpg   # enroll from files (3–5 shots, averaged)
python -m backend.preview --match S001      # live diagnostic window: aim/light the camera
python -m backend.calibrate --days 7        # tune FACE_THRESHOLD from real logged scores
```
(`--capture` webcam enrollment was fixed in Step 33 — it now uses `probe.embedding`. The
shared enroll core (`embeddings_from_frames`, `enroll_student`) is reused by the in-app
register wizard, Step 35.)

Env vars (incl. `USE_GPU`, `FACE_DET_SIZE`), camera setup, performance/GPU, threshold tuning, and troubleshooting: [`docs/face-verification.md`](docs/face-verification.md).

## Setup (first run)

One command brings up the whole stack (Postgres + backend) in Docker:

```
git clone <repo-url> nfc-scan && cd nfc-scan
cp .env.example .env      # then edit as needed
make up                   # docker-compose: db + backend, schema self-migrates
curl localhost:8001/health   # {"status":"ok","db":true}
make down                 # stop (keeps the pgdata volume)
```

`make` targets: `setup` (local venv + deps + models + .env), `up`/`down`/`logs`
(compose), `dev` (uvicorn --reload), `enroll`/`calibrate`/`preview`, `fmt`/`lint`,
`health`. Run `make` with no target for the list. Webcam passthrough for face match
is a commented `devices:` block in `docker-compose.yml` — uncomment on the kiosk box.

Or run it locally without Docker:

```
make setup                                  # venv, deps, fetch models, seed .env
. .venv/bin/activate

# Postgres (dev container, pgvector) — see "Running (production)" for the full command
docker run -d --name nfc-scan-postgres --restart unless-stopped \
  -p 5433:5432 -v nfc-scan-pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
  pgvector/pgvector:pg16

make dev                                    # uvicorn :8001, schema self-migrates
```

The InsightFace `buffalo_l` face model auto-downloads once to `~/.insightface` on first tap.
All configuration is env-driven — see [`.env.example`](.env.example) for every knob. Nothing in
the repo is a secret; SMTP credentials and DB DSN come from your environment.

## Liveness, guardian email & enforcement (Steps 7–9)

One webcam capture per tap feeds both face match and liveness. `decision.decide()` collapses
the two factors into a per-tap `status` stored on `attendance_logs`:

`accepted` (all available factors passed) · `flagged` (a factor failed, enforcement off — still
present) · `rejected` (a factor failed, enforcement on — not counted, still stored for audit) ·
`unverified` (no verdict, fail-open) · `unregistered` (unknown card).

All checks stay **fail-open**: a missing camera / reference / model leaves scores NULL and the tap
still logs. Enforcement only ever acts on an *explicit* fail.

```
# Liveness (Step 7) — MiniFASNet anti-spoof
LIVENESS_ENABLED=true            # default
LIVENESS_THRESHOLD=              # unset -> model argmax; set p_live cutoff after calibration
python -m backend.fetch_liveness_models          # one-time weight download (already present here)
python -m backend.calibrate --metric liveness    # tune the threshold from logged scores

# Guardian email (Step 8) — off until SMTP is configured
NOTIFY_EMAIL_ENABLED=false       # default (console-only). Set true to email guardians
SMTP_HOST= SMTP_PORT=587         # 465 -> implicit SSL, else STARTTLS
SMTP_USER= SMTP_PASSWORD= SMTP_FROM=
SMTP_STARTTLS=true SMTP_TIMEOUT=10

# 2FA enforcement (Step 9) — buddy-punch / photo-spoof rejection
ENFORCE_2FA=false                # default. true -> failed factor => status 'rejected'
```

## Running (production — systemd)

Backend and serial reader run as user-level systemd services with `Restart=always`, so they survive crashes and restart automatically:

```
systemctl --user status nfc-scan-backend nfc-scan-reader
journalctl --user -u nfc-scan-backend -u nfc-scan-reader -f   # live logs
systemctl --user restart nfc-scan-backend                     # after a code change
```

Unit files: `~/.config/systemd/user/nfc-scan-backend.service`, `~/.config/systemd/user/nfc-scan-reader.service`.

Postgres runs in Docker with a persistent volume and its own restart policy (survives host reboot regardless of user login, since dockerd is a system service):
```
docker run -d --name nfc-scan-postgres --restart unless-stopped \
  -p 5433:5432 -v nfc-scan-pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
  pgvector/pgvector:pg16
```

**Boot-independent start for the systemd user services still needs one manual step**: `sudo loginctl enable-linger scylla` — without it, the backend/reader units only start once this user logs in, not at pure boot.

Default `DB_DSN` in `backend/db.py` points at the dev container (`localhost:5433`). Override via env var to point elsewhere.

## Running (manual / dev)

```
uvicorn backend.main:app --host 0.0.0.0 --port 8001
TAP_URL=http://localhost:8001/tap python3 -m backend.serial_reader
```
(needs Arduino IDE's Serial Monitor closed first — only one process can hold `/dev/ttyACM0`; also stop the systemd services first, or they'll fight over the port/serial device)

Reflashing the Arduino:
```
arduino-cli compile --fqbn arduino:avr:uno arduino/nfc_scan
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/nfc_scan
```
(`arduino-cli` ships inside the Arduino IDE flatpak if not on PATH — see project CLAUDE.md for the bundled path.)

## Status

- [x] RC522 reads UID, relay only (no on-device whitelist)
- [x] Serial → FastAPI `/tap` → Postgres logging
- [x] Notify stub (print) fires on tap, registered or not
- [x] End-to-end test loop with a fake student (`S001`)
- [x] 24/7 hardening: systemd services (auto-restart), persistent Postgres volume, serial reconnect, failed-tap retry queue
- [x] Face detection integration (1:1 match) — InsightFace `buffalo_l`, fail-open, best-of-N probe; verified live 2026-07-10 (genuine 0.86 / impostor 0.018)
- [x] Passive liveness (MiniFASNet) — built + wired into `/tap` (`backend/liveness.py`, ensemble V2@2.7 + V1SE@4.0, fail-open). ⚠ needs live threshold calibration before enforcing (see below)
- [x] Real SMTP guardian notify — `backend/notify.py` emails the guardian when configured; console line always prints. Off until `SMTP_*` set. ⚠ not sent against a live provider yet
- [x] Buddy-punch mitigation (2FA enforced) — `backend/decision.py` collapses face+liveness into a per-tap `status`; `ENFORCE_2FA` rejects a failed 2nd factor. **Off by default** (fail-open preserved). ⚠ flip on only after live validation

## Roadmap

Next up is the user-facing layer plus a continuous multi-student guardpost. The ordered build plan
is in [`ROADMAP.md`](ROADMAP.md):
- **UI track (10–16)** — one-command setup ✓ (Step 10), API + live stream ✓ (Step 11:
  `GET /api/attendance|students|stats/today|config`, `WS /ws/taps`, `OPERATOR_TOKEN` auth),
  SPA scaffold ✓ (Step 12: Vite+React+TS `frontend/`, served at `/app`), operator dashboard ✓
  (Step 13: auth gate, today panel, live feed, history table).
- **Backbone track (20–23)** — privacy/compliance ✓ (Step 20: consent gate, retention/purge,
  right-to-erasure, audit log — see [`docs/privacy.md`](docs/privacy.md)), attendance sessions +
  digest, reliability, anti-fraud.
- **Flow track (30–35)** — continuous perception ✓ (Step 30: `backend/perception.py`,
  single camera owner, IoU tracking, recognition once per track) + tap↔face correlation ✓
  (Step 31: `backend/matcher.py`, async tap buffer + Hungarian, statuses
  accepted/mismatch/no_face/spoof/tailgating) for a 3–5 students/sec guardpost,
  boxes-only public viewer, in-app register wizard, review queue.
- **Deploy track (40–44)** — one-touch install onto the GPU box as a boot-on appliance (Linux primary, Windows `.exe` fallback), in-UI first-run wizard, updates/backup, release CI.
- **Tuning track (50–54)** — admin runtime panel: GPU/CPU device toggle, resolution presets + advanced, and an optimizer (auto-detect button, presets, adaptive), all hot-applied without a restart.

Cross-cutting constraints, failure modes, edge cases, and the legal/consent + accuracy-eval gates
are in [`docs/design-notes.md`](docs/design-notes.md) — **read it before starting the Flow track.**

A step-by-step **verification runbook** for everything built so far (Steps 10–33) is in
[`docs/verification.md`](docs/verification.md); data-handling/consent/retention is in
[`docs/privacy.md`](docs/privacy.md).

## Notes

UID alone is cloneable (magic cards). Not used as sole security — paired with face detection as 2nd factor.

UID format from the relay-only firmware: uppercase hex, no separators (e.g. `C3BE343A`). Older firmware (now replaced) emitted spaced hex (`C3 BE 34 3A`) — any `students.uid` rows created against the old firmware need re-normalizing to the no-space format if the board gets reflashed again.

## License

Apache-2.0 — see [`LICENSE`](LICENSE). Third-party model attribution (MiniFASNet, InsightFace) and the InsightFace non-commercial model note are in [`NOTICE`](NOTICE).
