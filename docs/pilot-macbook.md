# Pilot on the MacBook Air: bring-up checklist (18 Nov 2026)

For whoever sets up the MacBook Air 2016 for the pilot, person or Claude CLI. The Acer
Nitro 5 is away, so the pilot runs on the MacBook. Work through the steps in order and
report each result.

Rules while doing this:

- Never print `.env` (`cat`, `less`, `grep` with values). Check a value by its length
  only. `.env` holds secrets and is git-ignored; never commit it.
- This repo is public. Study account details (the study Gmail address and its recovery
  details) live in the private safe-paper repo, not here. Do not write them into any
  tracked file, commit message or issue.
- No live SMS: `NOTIFY_SMS_ENABLED` stays `false`.

## 1. Update the code

```bash
git pull                          # main, at 23be832 or later
pip install -r requirements.txt   # no new packages since 17 Nov; harmless to re-run
cd frontend && npm ci && npm run build && cd ..   # the dashboard changed on 18 Nov
```

`frontend/dist` is not in git. Without the rebuild the old dashboard is served.

The database schema updates itself when the backend starts (`db.init_db()` runs
`backend/schema.sql`: the `revoked_cards` table, nullable card UID, PC-024).

## 2. `.env` on the MacBook

Add or change these lines. Edit the file in an editor (`nano .env`).

```bash
# Speed on the MacBook (operations.md, macOS)
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
PERCEPTION_STATS_SEC=30

# Guardian email (PC-026). Live-tested on 18 Nov from the desktop.
NOTIFY_EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USER=<the study Gmail address: ask Cabucos>
SMTP_FROM=<same address>
SMTP_PASSWORD=<the study Gmail app password: Cabucos types it in, 16 letters, no spaces>

# SMS stays off until the sender name is approved
NOTIFY_SMS_ENABLED=false
```

Cabucos types `SMTP_PASSWORD` and `SEMAPHORE_API_KEY` in. Check them only with:

```bash
awk -F= '/^SMTP_PASSWORD=/{print "SMTP_PASSWORD length", length($2)}' .env   # expect 16
```

## 3. Start

```bash
make dev-cam      # backend in this terminal, so macOS gives it the camera
```

and the serial reader in a second terminal:

```bash
python -u -m backend.serial_reader   # posts taps to http://localhost:8001/tap
```

The Arduino is `/dev/cu.usbmodem*`.

## 4. Checks

1. `curl -s localhost:8001/health` gives `"status":"ok","db":true`.
2. Open `http://localhost:8001/app/`. The dashboard has the camera on the left, History
   and Live Feed on the right.
3. Within 30 s the Live Feed shows
   `[perception] N fps, detection N ms a frame, N camera frames skipped`. Write the
   numbers down. About 5 fps is expected on this machine; the lag should no longer grow.
4. On the Register page, stand where students will stand. The face must be reported as
   large enough at 640x480 (`MIN_FACE_PX` 80). If not, go back to 1280x720.
5. Tap an enrolled card with the face in view. The scan steps run under the camera and
   the verdict comes about 4 s after the tap (`ASSOC_WINDOW_SEC`; a fixed wait, by design).
6. Close the browser tab with the camera when nobody watches it; each viewed frame
   costs a JPEG encode.

## 5. Report back

The fps and detection numbers, the face size result, one tap's verdict and how long it
took, and anything in the Live Feed in red.

Background: `docs/build-log.md` (18 Nov entries), `docs/operations.md` (macOS),
`docs/phone-offload.md` (on hold).
