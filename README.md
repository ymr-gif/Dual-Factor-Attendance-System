# Dual-Factor Attendance System (nfc-scan)

Attendance logging for a school guardpost. A student taps an NFC card on an RC522 reader, which
says who they claim to be. A camera then checks that the face at the kiosk belongs to that student
and is a live person, not a photo. A card UID on its own can be cloned or lent to a friend, so the
face check is the second factor.

**Status: research prototype, not production-ready.** It processes children's biometrics and the
safeguards a real deployment needs are not finished. Read
[Limits and next steps](#limits-and-next-steps) before putting real student data in it. The
InsightFace `buffalo_l` face model it uses is licensed for non-commercial research only (see
[`NOTICE`](NOTICE)).

This repository holds the code: Arduino sketch, FastAPI backend, React operator UI and install
scripts. The research proposal defense for the project (S.A.F.E.) is in
[dual-factor-attendance-defense](https://github.com/ymr-gif/dual-factor-attendance-defense).

## How it works

1. The Arduino sketch (`arduino/nfc_scan/`) reads the card UID and prints it over USB serial. It
   makes no decision.
2. `backend/serial_reader.py` forwards each UID to `POST /tap`.
3. The backend (`backend/main.py`) looks the UID up in Postgres, checks the face with InsightFace
   `buffalo_l` (cosine similarity against `FACE_THRESHOLD`, default 0.5) and liveness with
   MiniFASNet, and writes one row to `attendance_logs` with a `status`. A face is stored as a
   512-number embedding in `students.face_embedding` (pgvector). No photo is written to disk.
4. Each result prints a console line, reaches the operator UI at `/app` over a WebSocket, and can
   be emailed to the student's guardian.

`PERCEPTION_ENABLED` chooses how the camera is used. On (the value in `.env.example` and in the
installed services): a perception loop owns the camera and a matcher pairs each tap with a face
seen within `ASSOC_WINDOW_SEC` (default 4 seconds) of it. For an enrolled card `/tap` answers
`queued` and the verdict is logged when that window closes. Off (the code default, used by
`make dev`): `/tap` captures a few frames itself and returns the verdict in its response.

| Status | Written when |
|---|---|
| `accepted` | Every factor that ran passed, or the matcher paired the tap with the enrolled face. |
| `flagged` | A factor explicitly failed and `ENFORCE_2FA` is off. |
| `rejected` | A factor explicitly failed and `ENFORCE_2FA` is on. |
| `unverified` | Known card, but no factor could run (no camera, no enrolled face, no consent). |
| `unregistered` | The card is not on the roster. |

The matcher also writes `no_face` (no face in the tap's window), `mismatch` (a face scored below
the threshold), `spoof` (the face matched but a calibrated liveness check said not live) and
`tailgating` (a face with no tap to claim it). Every status name is a constant in
`backend/decision.py`.

The checks fail open. A factor that cannot run is stored as NULL, not as a failure, and the tap is
still logged. A dead camera never blocks a tap; it shows up as `unverified` or `no_face`.

## Install

Needs Debian/Ubuntu or macOS with git, Docker, Node.js and Python 3.10 to 3.12.

```bash
curl -fsSL https://raw.githubusercontent.com/ymr-gif/Dual-Factor-Attendance-System/main/deploy/bootstrap.sh | bash
```

As with any `curl | bash`, read [`deploy/bootstrap.sh`](deploy/bootstrap.sh) first. It clones the
repo to `~/nfc-scan` and runs `deploy/install.sh`, which writes `.env`, creates `.venv`, starts
Postgres 16 with pgvector in Docker on port 5433, downloads the liveness models, builds the web UI,
and registers the backend and the serial reader as auto-start services (systemd user units on
Linux, launchd agents on macOS). Then open `http://localhost:8001/app/setup`.

From a checkout, `make appliance` runs the same installer and `make up` starts Postgres and the
backend under Docker Compose instead. For development:

```bash
make setup                           # .venv, Python deps, liveness models, .env
docker compose up -d db              # Postgres on localhost:5433
make dev                             # backend on :8001 with autoreload
make web-install && make web-dev     # UI dev server at http://localhost:5173/app/
```

`make` with no target lists every command. On macOS inference is CPU-only and the Arduino appears
as `/dev/cu.usbmodem*`; prerequisites and launchd controls are in
[`docs/operations.md`](docs/operations.md#macos).

## Try it without hardware

```bash
curl -X POST localhost:8001/tap -H 'Content-Type: application/json' -d '{"uid":"CCF98E02"}'
curl -X POST localhost:8001/api/students -H 'Content-Type: application/json' \
  -d '{"student_id":"S001","uid":"CCF98E02","name":"Test Student"}'
curl -X POST localhost:8001/tap -H 'Content-Type: application/json' -d '{"uid":"CCF98E02"}'
curl 'localhost:8001/api/attendance?limit=5'
```

`/tap` is what the serial reader calls, so `curl` can stand in for a card. The first tap is logged
as `unregistered`. Once the card is on the roster, the second is logged for `S001` as `unverified`,
because there is no camera and no enrolled face. Taps also appear on the dashboard at `/app/`.

## Hardware

| RC522 | Arduino Uno |
|-------|-------------|
| SDA   | 10  |
| SCK   | 13  |
| MOSI  | 11  |
| MISO  | 12  |
| RST   | 9   |
| GND   | GND |
| 3.3V  | 3.3V |

Plus a USB webcam on the machine that runs the backend, selected with `CAMERA_INDEX` (default 0).
Flashing the sketch and the UID format are in [`docs/operations.md`](docs/operations.md#arduino).

## Configuration

Settings are environment variables. [`.env.example`](.env.example) lists them with their defaults,
and no secret is committed. These switches change what the system does:

| Variable | Default | Effect |
|---|---|---|
| `PERCEPTION_ENABLED` | `false` in code, `true` in `.env.example` | Continuous camera loop and tap-to-face matcher, instead of one capture per tap. |
| `ENFORCE_2FA` | `false` | A failed factor is stored as `rejected` instead of `flagged`. Read only when perception is off. |
| `LIVENESS_ENABLED` | `true` | Run the MiniFASNet liveness check. |
| `FACE_CONSENT_REQUIRED` | `false` | A student without recorded consent cannot be enrolled and gets no face check. |
| `NOTIFY_EMAIL_ENABLED` | `false` | Email the guardian for each logged tap. Needs `SMTP_HOST` and the other `SMTP_*` values. |
| `OPERATOR_TOKEN` | empty | When set, `/api/*` (except `/api/setup/status`) and the `/ws/taps` WebSocket require it. When empty they are open. |
| `USE_GPU` | `false` | Run both models on CUDA, falling back to CPU if it is unavailable. |

`.env` is read by the installed services and by Docker Compose. A process started by hand,
`make dev` included, sees only its shell environment ([details](docs/operations.md#running-by-hand)).

## Limits and next steps

Required before real use, and not done:

- The subjects are children and face embeddings are biometric data. No data protection impact
  assessment (DPIA) exists, and the consent gate `FACE_CONSENT_REQUIRED` is off by default.
- Face embeddings are not encrypted at rest, and `deploy/backup.sh` dumps them as plain SQL.
- With `OPERATOR_TOKEN` unset the operator API is open to anyone who can reach port 8001. When set
  it is one shared token, with no per-user roles. `/tap`, `/metrics` and `/stream.mjpeg` never ask
  for a token, and the stream (shown by the Viewer page) is the live camera image with face boxes.
- `buffalo_l` may not be used commercially without obtaining rights ([`NOTICE`](NOTICE)).

Built, but not verified or not finished:

- Face match was checked live on 2026-07-10 with one enrolled student: genuine 0.86, impostor
  0.018, against the 0.5 threshold ([record](docs/face-verification.md#verification-record)). That
  is a working check, not an accuracy evaluation.
- `LIVENESS_THRESHOLD` is unset, so liveness is not calibrated against real spoof attempts. Until
  it is set, the matcher records the liveness score and does not act on it.
- Guardian email has not been sent through a live SMTP provider, and throughput on the intended
  GPU machine has not been measured.
- The status does not yet affect the count. `decision.counts_as_present()` defines which statuses
  should count as attendance, but nothing calls it: `GET /api/attendance/summary` counts a student
  present after any tap of their card, `rejected`, `mismatch` and `spoof` included. The Review page
  and `/api/review` exist, but nothing adds rows to `review_queue`.

Next, in order: calibrate liveness against real spoof attempts and then enforce it; send email
through a live provider; make the present count and the review queue use the per-tap status;
measure throughput against the target of 3 to 5 students per second. Constraints and failure modes
are in [`docs/design-notes.md`](docs/design-notes.md).

## Development

```bash
python3 -m venv .venv                             # skip if `make setup` already made it
.venv/bin/pip install -r requirements-dev.txt
make test
```

The tests need no database, camera, model files or network: `tests/conftest.py` replaces them with
in-memory fakes and stubs the heavy packages that are not installed. They cover the status truth
table (`tests/test_decision.py`) and `/tap` and `/health` through FastAPI's test client
(`tests/test_tap.py`). The matcher, the SQL, the UI and the install scripts have no tests yet.

## Docs

- [`docs/operations.md`](docs/operations.md): services, macOS, manual runs, database, settings, CLI tools, Arduino.
- [`deploy/README.md`](deploy/README.md): the installer, kiosk screen, backup, restore, update.
- [`docs/design-notes.md`](docs/design-notes.md): constraints, failure modes, legal and ethical gates.
- [`docs/face-verification.md`](docs/face-verification.md): enrollment, thresholds, camera, GPU, the live record.
- [`docs/privacy.md`](docs/privacy.md): what is stored, consent, retention, erasure.
- [`docs/verification.md`](docs/verification.md): manual checks for each built feature.
- [`docs/build-log.md`](docs/build-log.md): what each build step added.

## License

Apache-2.0, see [`LICENSE`](LICENSE). Third-party model attribution (MiniFASNet, InsightFace) and
the InsightFace non-commercial model note are in [`NOTICE`](NOTICE).
