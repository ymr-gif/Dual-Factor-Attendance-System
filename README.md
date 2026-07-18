# nfc-scan

Attendance logging system. NFC (RC522) + face detection, 2-factor.

## Structure

- `arduino/nfc_scan/` — Arduino sketch, RC522 UID read, relay only (no on-device auth decision)
- `backend/` — FastAPI + Postgres logging service

## Architecture (locked)

- Arduino → UID over serial → laptop (relay only, no whitelist/decision on-device)
- FastAPI backend (`backend/main.py`)
- Postgres: `students` (uid → identity, `face_embedding`) + `attendance_logs` (student_id, timestamp, method, liveness_score, face_score, face_match)
- SMTP: guardian notify (currently a print stub, see `backend/notify.py`)
- InsightFace `buffalo_l` (ArcFace, 512-d): 1:1 match — NFC identifies, face verifies (built, Step 6). Chosen over `face_recognition`/dlib: no compile, better on off-angle/uneven-light faces.
- MiniFASNet (Silent-Face-Anti-Spoofing): passive liveness (not yet built)

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
python -m backend.enroll S001 --capture 5   # enroll from webcam (3–5 shots, averaged)
python -m backend.preview --match S001      # live diagnostic window: aim/light the camera
python -m backend.calibrate --days 7        # tune FACE_THRESHOLD from real logged scores
```

Env vars (incl. `USE_GPU`, `FACE_DET_SIZE`), camera setup, performance/GPU, threshold tuning, and troubleshooting: [`docs/face-verification.md`](docs/face-verification.md).

## Setup (first run)

```
git clone <repo-url> nfc-scan && cd nfc-scan
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m backend.fetch_liveness_models     # sha256-pinned MiniFASNet weights (~3.4MB)
cp .env.example .env                        # then edit as needed

# Postgres (dev container, pgvector) — see "Running (production)" for the full command
docker run -d --name nfc-scan-postgres --restart unless-stopped \
  -p 5433:5432 -v nfc-scan-pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
  pgvector/pgvector:pg16

uvicorn backend.main:app --port 8001        # schema self-migrates on startup
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

Next up is the user-facing layer (operator dashboard, browser enrollment, kiosk feedback screen,
one-command setup). The ordered build plan is in [`ROADMAP.md`](ROADMAP.md) — Steps 10–16, each
with dependencies and acceptance checks.

## Notes

UID alone is cloneable (magic cards). Not used as sole security — paired with face detection as 2nd factor.

UID format from the relay-only firmware: uppercase hex, no separators (e.g. `C3BE343A`). Older firmware (now replaced) emitted spaced hex (`C3 BE 34 3A`) — any `students.uid` rows created against the old firmware need re-normalizing to the no-space format if the board gets reflashed again.

## License

Apache-2.0 — see [`LICENSE`](LICENSE). Third-party model attribution (MiniFASNet, InsightFace) and the InsightFace non-commercial model note are in [`NOTICE`](NOTICE).
