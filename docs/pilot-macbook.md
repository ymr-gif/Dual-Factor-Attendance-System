# Pilot on the MacBook Air: bring-up, tests and records (18 Nov 2026)

For whoever runs the MacBook Air 2016 for the pilot, person or Claude CLI. A Claude
session on the MacBook: read this whole file first, then work through it in order and
report each result to Cabucos. Code at `fbafb3e` or later.

## 0. Context

- S.A.F.E. is a Senior High School research prototype at Hua Siong College of Iloilo:
  an NFC card tap plus a face check (InsightFace 1:1 match, passive liveness) at the
  entrance, with an email to a guardian. The research paper lives in a separate,
  private repo; this repo is the code.
- Pilot: Thursday 19 Nov 2026, Ledesco Campus, at least 30 participants, up to 3 hours.
  Team on site: Cabucos (group leader), Loreno, Aragon.
- The Acer Nitro 5 is away, so the pilot runs on this MacBook (2 cores, CPU only).
  Measured 17 Nov: about 5 fps with a growing lag. Fixed 18 Nov (newest-frame reader,
  `55cae46`); not yet measured on the MacBook.
- Guardian channel for the pilot: email only, through the study Gmail (live-tested 18
  Nov, 3 of 3 arrived). SMS stays off until the telcos approve the sender name.
- What changed on 18 Nov, so you know what you are testing:
  - Dashboard: camera left; History (the day's taps) and Live Feed (the backend's own
    log) right; scan steps under the camera (`f9243d6`).
  - Newest-frame camera reader and a speed line in the log (`55cae46`).
  - Enrollment stays out of attendance (`c44725a`, `fbafb3e`): a card scanned into
    Register (Scan UID) or Roster (New card) is not logged; faces at the camera are not
    flagged while Register is open (15 min at most); a student accepted moments ago who
    stays in view makes no `tailgating` row.
  - The Guardian scan step shows the real result: "sending guardian email", then
    "guardian email sent in N s" or "not sent (reason)".

## Rules for this session

- Never print `.env` (`cat`, `less`, `grep` with values). Check a value by its length
  only. `.env` holds secrets and is git-ignored; never commit it.
- This repo is public. No study account details (the study Gmail address, recovery
  details), no participant names, emails or mobiles in any tracked file, commit message
  or issue. Test students may be called "Test 1", "Test 2".
- No live SMS: `NOTIFY_SMS_ENABLED` stays `false`.
- Never delete database rows, students or faces without Cabucos saying yes in the
  chat for that deletion. Never commit face data, database dumps, `failed_taps.jsonl`.
- Git: stage files by name; no `--force`, `reset --hard`, `rebase` or `clean`. Commit
  only code fixes and the findings file (section 6). No Claude attribution in commits.
- Tests: `python -m pytest tests -q` (497 passed, 11 skipped on 18 Nov).

## 1. Update the code

```bash
git pull                          # main, at fbafb3e or later
pip install -r requirements.txt   # no new packages since 17 Nov; harmless to re-run
python -m backend.fetch_liveness_models   # skip if backend/models/anti_spoof has 2 .onnx files
cd frontend && npm ci && npm run build && cd ..   # the dashboard changed on 18 Nov
```

`frontend/dist` is not in git. Without the rebuild the old pages are served, and
Register and Roster still log the cards they read.

The database schema updates itself when the backend starts (`db.init_db()` runs
`backend/schema.sql`).

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

The Arduino is `/dev/cu.usbmodem*`. Keep both terminals open; their output is the log.

## 4. Checks

1. `curl -s localhost:8001/health` gives `"status":"ok","db":true`.
2. Open `http://localhost:8001/app/`. The dashboard has the camera on the left, History
   and Live Feed on the right.
3. Within 30 s the Live Feed shows
   `[perception] N fps, detection N ms a frame, N camera frames skipped`. Write the
   numbers down. About 5 fps is expected on this machine; the lag should not grow.
4. On the Register page, stand where students will stand. The face must be reported as
   large enough at 640x480 (`MIN_FACE_PX` 80). If not, go back to 1280x720.
5. Close the browser tab with the camera when nobody watches it; each viewed frame
   costs a JPEG encode.

## 5. Tests to run today (dry run)

Use one or two test students. Write each result into the findings file (section 6).

| # | Do | Expect |
|---|---|---|
| T1 | Register: new student "Test 1", press Scan UID, tap a spare card, capture the face, save | UID field fills; History shows no row; Live Feed shows `[enroll] card ... not logged as attendance`; no `tailgating` row while Register is open |
| T2 | Close Register. Roster: open New card for Test 1, tap another spare card, Link | Field fills; no row in History; the old card is reported lost |
| T3 | Tap Test 1's card, face in view | `accepted`; scan steps run; Guardian step ends "guardian email sent in N s"; the email arrives |
| T4 | Same as T3, then stay in view for a minute | One `accepted` row, no `tailgating` rows after it; Live Feed: `matches a student accepted in the last 60 s, not flagged` |
| T5 | Someone not enrolled stands in view, no tap | One `tailgating` row, not one a minute |
| T6 | Tap Test 1's card with another person's face | `mismatch`; no email |
| T7 | Tap, then look away for the 4 s | `no_face`; no email |
| T8 | Tap the card reported lost in T2 | `revoked`; name on the dashboard, not on the kiosk; no email |
| T9 | Unplug the camera for 10 s, plug it back | Log says the camera stopped, then works again within about 5 s with no restart |
| T10 | Time five taps from tap to verdict | About 4 s each (`ASSOC_WINDOW_SEC`, by design) |

Liveness calibration (PC-025), after T1 to T10, in the pilot's lighting if possible:

1. Genuine round: write the start time (HH:MM). 20 to 30 taps by live, enrolled faces.
   Write the end time.
2. Spoof round: write the start time. Hold a printed photo, then a phone showing a
   face video, to the camera, with a tap each time, 20 to 30 times in total. End time.
3. Run, with your times:

   ```bash
   python -m backend.calibrate --metric liveness --since 14:00 --until 14:20 \
       --against-since 14:25 --against-until 14:45
   ```

4. Send Cabucos the output. If the two rounds separate, put the suggested threshold on
   the Settings page (`liveness_threshold`) after Cabucos agrees. Leave it empty if they
   overlap badly; then a spoof is only flagged, not refused.

## 6. Record the results

Write `docs/findings-2026-11-18-macbook.md` and commit it with a message like
"MacBook dry run 18 Nov: results". Use this outline:

```markdown
# MacBook dry run, 18 Nov 2026

Machine: MacBook Air 2016, macOS <version>, commit <hash>. Camera: A4tech at 640x480.

## Speed
- [perception] lines: <fps>, <detection ms>, <skipped> (copy 3 lines)
- Tap to verdict: <five times in seconds>

## Tests
| # | Result | Notes |
|---|---|---|
| T1 | OK / FIX | ... |

## Liveness calibration
- Genuine round <times>, spoof round <times>
- calibrate output: <paste>
- Threshold saved: <value or none>

## Problems
- <what happened, the Live Feed lines around it, what was done>
```

No participant or study account details in it; test students only.

## 7. Before the pilot (do not do this without Cabucos's yes)

The pilot should start with no test rows. With Cabucos's yes in the chat:

```bash
# today's test taps only; students and faces stay
docker exec nfc-scan-postgres psql -U attendance -d attendance -c \
  "DELETE FROM attendance_logs WHERE (ts AT TIME ZONE 'Asia/Manila')::date = (now() AT TIME ZONE 'Asia/Manila')::date;"
```

Test students: ask Cabucos whether to erase them (Roster, Delete) before enrolling the
pilot participants.

On site: enroll each participant on Register (about 1 to 2 minutes each), close Register
before entries start, keep the Live Feed visible to the operator.

## 8. Reading the Live Feed

| Line | Meaning |
|---|---|
| `[scan] UID card: card read` ... `verdict: accepted` | One tap going through the steps |
| `[scan] UID notify: sending guardian email` / `guardian email sent in 3.9 s` | The email left; the second line is the measured latency |
| `[scan] UID notify: no guardian message (no guardian email on file, SMS off)` | Nothing sent: the student has no guardian email |
| `[matcher] tap uid=...: window closed, N face event(s) ... paired with track T` | Which face the tap was judged against |
| `[matcher] face with no tap, track T: nearest remembered face 0.44 ...` | A face nobody tapped for; a `tailgating` row follows |
| `[matcher] ... matches a student accepted in the last 60 s, not flagged` | The student who just tapped, still in view |
| `[matcher] ... enrollment in progress, not flagged` | Register is open |
| `[enroll] card UID read for enrollment: not logged as attendance` | A card scanned into Register or Roster |
| `[perception] track T: face N px recognized in N ms, liveness 0.93 (live)` | A new face was measured |
| `[perception] N fps, detection N ms a frame` | Speed, every 30 s |
| Red lines | Errors: copy them into the findings file |

## 9. Trouble

- No camera picture: the backend must run from a terminal (`make dev-cam`), not
  launchd; macOS gives the camera to the terminal app. `hardware-troubleshooting.md`.
- Reader prints nothing on a tap: check `/dev/cu.usbmodem*` and that only one program
  holds the port.
- Every face "not live": light from the front, not behind the person.
- fps under 3: close the dashboard camera tab, check nothing else uses the CPU.

Background: `docs/build-log.md` (18 Nov entries), `docs/operations.md` (macOS),
`docs/phone-offload.md` (on hold).
