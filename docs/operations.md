# Operations

Day-to-day running of an installed nfc-scan box: services, macOS specifics, manual runs,
the database container, the settings that change behaviour, the command-line tools and
the Arduino. Installing, the kiosk screen, backup and update are in
[`deploy/README.md`](../deploy/README.md). What the system does not yet do safely is in the
[README](../README.md#limits-and-next-steps).

## What runs

| Piece | What it is | Linux (systemd user unit) | macOS (launchd agent) |
|---|---|---|---|
| Database | Postgres 16 + pgvector in Docker, container `nfc-scan-postgres`, host port 5433 | container restart policy `unless-stopped` | same, under Docker Desktop |
| Backend | `uvicorn backend.main:app` on port 8001 | `nfc-scan-backend` | `com.nfc-scan.backend` |
| Serial reader | `python -m backend.serial_reader`, posts each card UID to `/tap` | `nfc-scan-reader` | `com.nfc-scan.reader` |

Only one process can hold the camera and only one can hold the serial port. Stop the
matching service before running `backend.preview`, the Arduino IDE Serial Monitor, or a
second copy of the backend or reader by hand.

## Linux (systemd)

The installer copies `deploy/systemd/*.service` into `~/.config/systemd/user/`, fills in
the checkout path and the Python interpreter, and enables both units. Status, restart and
log commands, and what to do when a restart hangs, are in
[`deploy/README.md`](../deploy/README.md#services).

**Start at boot.** User units start when their user logs in. To start them at boot with
nobody logged in, the user needs lingering enabled. The installer tries this and prints
the command if it lacks permission:

```bash
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" --property=Linger     # Linger=yes when it is on
```

**Device access.** The service user must be in the `video` group (webcam) and the
`dialout` group (serial). `make preflight` reports both and prints the `usermod` command
for whichever is missing.

**After a code change** restart the unit. Nothing watches for edits under systemd:

```bash
systemctl --user restart nfc-scan-backend
```

## macOS

The same installer runs on macOS. Three things differ from Linux:

- Auto-start uses launchd agents in `~/Library/LaunchAgents/` instead of systemd units.
- There is no CUDA, so inference runs on the CPU. Leave `USE_GPU=false`.
- The Arduino appears as `/dev/cu.usbmodem*`. The installer writes the first one it finds
  to `.env` as `SERIAL_PORT`. The camera is chosen by `CAMERA_INDEX` (default 0); there is
  no `/dev/video0`.

Prerequisites, once:

```bash
xcode-select --install          # build tools, needed to install insightface
brew install python@3.11 node
# Install Docker Desktop from https://www.docker.com/products/docker-desktop and start it.
```

Then install as on Linux (`make appliance` from a checkout, or the one-line installer in
the README). The installer reminds you to grant Camera access when macOS asks.

launchd controls:

```bash
launchctl list | grep nfc-scan                                         # are the agents loaded?
launchctl unload ~/Library/LaunchAgents/com.nfc-scan.backend.plist     # stop
launchctl load   ~/Library/LaunchAgents/com.nfc-scan.backend.plist     # start
tail -f backend.launchd.log reader.launchd.log                         # logs, in the checkout
```

Replace `backend` with `reader` for the serial reader. The backup and restore scripts in
`deploy/` work unchanged. `deploy/update.sh` and `deploy/factory-reset.sh` restart the
services only where `systemctl` exists, so on macOS reload the agents yourself afterwards.

## Editing `.env`

Three things read `.env`, and they parse it differently: systemd (`EnvironmentFile=`), a
shell (`set -a; . ./.env; set +a`, which is what the launchd wrappers do) and Docker Compose
(`env_file`). Two rules keep all three in agreement:

- Put every comment on its own line. systemd keeps a trailing `# comment` as part of the
  value, and Compose does the same when the value is empty.
- Double-quote any value that contains a space, such as `DB_DSN`. A shell otherwise cuts
  it at the first space.

`.env.example` follows both rules. A `.env` created from an older copy of it does not: its
`CAMERA_INDEX` reaches the backend as `0   # USB webcam; ...`, `backend/face.py` raises
`ValueError` on import, and the systemd unit restarts in a loop. The installer leaves an
existing `.env` untouched, so clean such a file once and restart:

```bash
cd ~/nfc-scan      # or wherever the checkout lives
sed -i.bak -E -e 's/[[:space:]]+#.*$//' -e 's/^DB_DSN=([^"].*)$/DB_DSN="\1"/' .env && rm .env.bak
systemctl --user restart nfc-scan-backend nfc-scan-reader     # Linux
```

On macOS, unload and load both agents instead of the last line.

## Running by hand

Useful for a demo, for development, or after `NFC_NO_AUTOSTART=1 make appliance`
(provision everything, install no services). Stop the services first if they exist.

```bash
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
TAP_URL=http://localhost:8001/tap .venv/bin/python -m backend.serial_reader
```

- `make dev` is the first command plus `--reload`.
- A process started by hand reads its own environment only. Nothing loads `.env` for it,
  so it runs on the code defaults, which include `PERCEPTION_ENABLED=false`. Pass settings
  inline (`ENFORCE_2FA=true make dev`) or export the file first with
  `set -a; . ./.env; set +a` (see [Editing `.env`](#editing-env) above).
- The reader's built-in `TAP_URL` default is port 8000, so set it as shown. `SERIAL_PORT`
  defaults to `/dev/ttyACM0` and `SERIAL_BAUD` to 9600. On macOS use
  `SERIAL_PORT=/dev/cu.usbmodemXXXX` (`ls /dev/cu.*` lists the candidates).
- Keep the backend at one worker. The tap buffer, the event bus and the loaded models
  live in process memory (see [`design-notes.md`](design-notes.md), section 3).

The reader reconnects when the Arduino is unplugged and replugged. A tap it cannot
deliver is appended to `backend/failed_taps.jsonl` and retried on the next tap.

## Docker Compose stack

`make up` builds and starts Postgres and the backend in containers. `make logs` tails them and
`make down` stops them, keeping the data volume.

- Inside the Compose network the backend reaches Postgres as `db:5432`. `docker-compose.yml`
  sets `DB_DSN` to that, whatever `.env` says.
- The backend container has no camera unless you pass one in. Webcam passthrough is a
  commented `devices:` block in `docker-compose.yml`.
- The serial reader is not part of the stack. Run it on the host as shown above.

## Database container

The installer creates the container with this command. Run it yourself to get the same
database without the installer:

```bash
docker run -d --name nfc-scan-postgres --restart unless-stopped \
  -p 5433:5432 -v nfc-scan-pgdata:/var/lib/postgresql/data \
  -e POSTGRES_DB=attendance -e POSTGRES_USER=attendance -e POSTGRES_PASSWORD=attendance \
  pgvector/pgvector:pg16
```

- Attendance history and face embeddings live in the named volume `nfc-scan-pgdata`.
  Removing the container keeps the data. Removing the volume deletes it.
- `make up` and `docker compose up -d db` start a container with the same name from
  `docker-compose.yml`, but Compose prefixes its volume with the project name
  (`<project>_nfc-scan-pgdata`). The two setups therefore cannot run side by side and do
  not share data. Pick one per machine.
- The backend's built-in `DB_DSN` points at this container (`localhost:5433`, user and
  password `attendance`). Those are development credentials. Set `DB_DSN` to point
  anywhere else.
- The schema is applied at every backend start from `backend/schema.sql`, which only
  adds what is missing. The backend retries for about 30 seconds if Postgres is not up yet.

## Settings that change behaviour

All settings are environment variables, listed with defaults in
[`.env.example`](../.env.example). They are read once, when the backend starts.

**Liveness (MiniFASNet anti-spoof)**

```bash
LIVENESS_ENABLED=true     # default
LIVENESS_THRESHOLD=       # unset: the model's own live/spoof verdict. Set a p_live cutoff after calibration.
```

```bash
python -m backend.fetch_liveness_models          # download the weights once (sha256-checked)
python -m backend.calibrate --metric liveness    # score distribution from logged taps
```

While `LIVENESS_THRESHOLD` is unset the tap-to-face matcher logs the liveness score but
does not turn a matched face into `spoof`.

**Guardian email**

```bash
NOTIFY_EMAIL_ENABLED=false    # default: console line only. true: also email the guardian.
SMTP_HOST=                    # required to send
SMTP_PORT=587                 # 465 uses implicit SSL, any other port uses STARTTLS
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=                    # defaults to SMTP_USER
SMTP_STARTTLS=true
SMTP_TIMEOUT=10
```

An SMTP error is printed and ignored. It never fails a tap.

**Two-factor enforcement**

```bash
ENFORCE_2FA=false    # default: a failed factor is stored as "flagged". true: stored as "rejected".
```

Enforcement acts only on an explicit failure. A factor that could not run (no camera, no
enrolled face, model error) never causes a rejection.

This switch is read by the direct path only (`PERCEPTION_ENABLED=false`, where `/tap`
calls `decision.decide()`). With perception on, the matcher writes `accepted`, `mismatch`,
`spoof`, `no_face` or `unverified` itself and `ENFORCE_2FA` has no effect: `mismatch` and
`spoof` never count as present either way.

**What counts as present, and the review queue**

`accepted`, `flagged` and `unverified` count toward attendance. `rejected`, `no_face`,
`mismatch`, `spoof` and `tailgating` do not. The summary, the late flag and the
`attendance_sessions` view all apply the same rule (`decision.counts_as_present()`).

Every tap that failed a check is added to the review queue (Review page, `GET /api/review`)
with the reason. The three resolutions:

- `override`: the operator vouches for the student. That tap now counts.
- `confirmed`: the flag was right. Nothing changes; the tap stays as its status says.
- `dismiss`: drop it from the queue without a judgement. Nothing changes.

A tap the camera never watched is the one `unverified` case that is also queued. The matcher
counts the camera frames that arrive inside each tap's own window. No frame at all means the
camera was down for that tap, so it is logged `unverified` (still counted, per the fail-open
rule), an `[ALERT]` line goes to the backend log, and the review entry carries the reason
`camera delivered no frame during the tap; card-only`.

**Attendance clock**

```bash
# ATTENDANCE_TZ=Asia/Manila    # unset: the zone of the machine the backend runs on
LATE_CUTOFF=08:00
```

Days and clock times are worked out in SQL, in the database session's time zone, and
Postgres in Docker runs on UTC. The backend therefore switches each session to
`ATTENDANCE_TZ`, or to its own machine's zone when that is unset. Without this, a 07:30 tap
in a UTC+8 school is filed under the previous day and compared with `LATE_CUTOFF` as 23:30.
Set `ATTENDANCE_TZ` when the backend's own clock is not the school's, which is the case under
Docker Compose (`make up`), where the backend container is on UTC as well. A zone name
Postgres does not know is reported once in the log and the session stays on UTC.

**Camera stream access**

`/stream.mjpeg` is the live camera image. When `OPERATOR_TOKEN` is set it needs either the
token in a header, or a ticket: `POST /api/stream-ticket` (token in a header) returns a
random ticket that opens the stream for 60 seconds, as `/stream.mjpeg?ticket=...`. The pages
do this themselves. The operator token is never accepted from the URL, because URLs end up in
access logs and browser history. A stream that is already open keeps running after its
ticket expires; the ticket only gates the connection.

GPU setup (`USE_GPU`) is in
[`face-verification.md`](face-verification.md#performance--gpu). Consent and retention
settings are in [`privacy.md`](privacy.md).

## Command-line tools

Run from the repo root with the backend's interpreter. `make enroll`, `make calibrate`,
`make preview` and `make digest` wrap the same commands and pass extra arguments through
`ARGS`. `make doctor` and `make purge` take none.

```bash
python -m backend.enroll S001 --images a.jpg b.jpg c.jpg   # enroll from files; 3 to 5 shots are averaged
python -m backend.enroll S001 --capture 5                  # enroll from the webcam
python -m backend.enroll S001 --consent --capture 5        # record biometric consent, then enroll
python -m backend.preview --match S001                     # live window for aiming and lighting the camera
python -m backend.calibrate --days 7                       # face score distribution, last 7 days
python -m backend.doctor                                   # one pass/fail line per subsystem
python -m backend.privacy                                  # apply the retention windows (make purge)
python -m backend.digest --dry-run                         # guardian digest for yesterday, printed only
```

- `preview` needs a display and holds the camera until you press `q`.
- `doctor` opens the camera and the serial port itself, so those two lines are only
  meaningful while the services are stopped.
- Enrollment and thresholds are explained in
  [`face-verification.md`](face-verification.md).

## Arduino

The sketch is `arduino/nfc_scan/nfc_scan.ino`. It needs the `MFRC522` library, which the
Arduino Library Manager provides. Flash it from the Arduino IDE, or with `arduino-cli`:

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/nfc_scan
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/nfc_scan
```

Stop the reader first (`systemctl --user stop nfc-scan-reader`), because the upload needs
the serial port. Use the `/dev/cu.usbmodem*` path on macOS.

**UID format.** The sketch prints one line per card, `UID:` followed by the UID as
uppercase hex with no separators, for example `UID:C3BE343A`. `/tap` trims and uppercases
what it receives and looks it up in `students.uid` exactly as written. If you change the
sketch's output format (to spaced hex, for example), update the stored `students.uid`
values to match, or every card will be logged as `unregistered`.
