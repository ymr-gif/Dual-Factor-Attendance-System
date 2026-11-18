# Nitro 5 (Windows) bring-up, 18 Nov 2026

Machine: Acer Nitro 5 (board out of its case — no chassis, so no built-in webcam),
Windows 11 Pro 10.0.26200, commit 560c8d4 (+ the `backend/cameras.py` fix below).
Camera: a Samsung Galaxy S24 over USB via DroidCam (see Camera section — the first
"working" camera found tonight turned out to be a false positive, corrected below).
Reader: Arduino Uno + RC522 on COM4.

## Section 1 — Update
- `git pull`: already at `560c8d4`.
- `py -3.11 -m venv .venv` + `pip install -r requirements.txt`: clean; `insightface`
  installed without needing a compiler (no Visual C++ Build Tools were present).
- `npm ci && npm run build`: clean.
- `docker compose up -d db`: `nfc-scan-postgres` healthy on `127.0.0.1:5433`.
- Docker Desktop and DroidCam Client both had to be installed from an already-elevated
  terminal — their installers hung indefinitely waiting for a UAC prompt that never
  rendered when launched from this non-interactive tool session.
- **Missed step, caught later**: this section (as written) never calls
  `python -m backend.fetch_liveness_models`, which `make setup` normally does. Liveness
  silently "fails open" (treats every face as live) until this is run manually — see
  Problems. Added it to the command list below for next time.

## Section 2 — .env
Created from `.env.example`. Non-secret values set: `CAMERA_WIDTH=1280`,
`CAMERA_HEIGHT=720`, `CAMERA_INDEX=0`, `PERCEPTION_ENABLED=true`, `USE_GPU=false`,
`PERCEPTION_STATS_SEC=30`, `NOTIFY_EMAIL_ENABLED=true`, `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, `SMTP_STARTTLS=true`, `NOTIFY_SMS_ENABLED=false`. Left blank for
Cabucos to fill in directly in the file: `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD`,
`SEMAPHORE_API_KEY`, `OPERATOR_TOKEN` — **still blank** as of shutdown tonight.

## Section 3 — Load `.env` and start
- `.env` loaded into the PowerShell process env; backend started with
  `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`.
- Health: `curl.exe -s localhost:8001/health` → `{"status":"ok","db":true}`.
- Dashboard: `GET /app/` → 200 OK.
- Serial reader (`python -u -m backend.serial_reader`): starts cleanly; printed
  "no serial port found — waiting for a board" before the Arduino was connected, then
  "listening on COM4 @ 9600" once it was.

## Section 4 — Tests
- `python -m pytest tests -q` → **497 passed, 11 skipped** — exact match to the Linux
  baseline (18 Nov). No Windows-only failures.
- T1–T10 and liveness calibration (`pilot-macbook.md` sections 4–5): **not run tonight**.
  Both the camera and reader are now confirmed live (see below), so nothing hardware-side
  blocks this anymore — it needs an in-person session to tap cards and stand in front of
  the camera, which didn't happen before the laptop had to be packed into its case.

## Camera — corrected finding
First pass tonight wrongly concluded the camera worked: `backend.cameras` reported "no
cameras reported by the OS" (that passive Windows check never found anything, all night —
see Problems), so `pick_index()` fell back to its default of index 0, and
`cv2.VideoCapture(0)` opened *something* and produced frames, which perception happily
measured at 12.4–12.9 fps. **Those frames were solid black** — this board has no case and
no built-in webcam, and index 0 was a leftover virtual camera (`VTubeStudioCam`, from
unrelated streaming software) that outputs a blank frame when its source app isn't
running. The fps numbers were real loop throughput over empty video, detecting nothing.
Caught by pulling a frame from the running backend's own `/stream.mjpeg` and looking at
it directly — worth doing that as a sanity check early next time, rather than trusting
`[perception] N fps` alone as proof the camera is real.

Once the phone was connected and the DroidCam app opened and connected (USB mode) on
both ends:
- Two virtual cameras exist on this machine: `VTubeStudioCam` and `DroidCam Source 2`
  (seen in the registry at `HKLM\SOFTWARE\Classes\CLSID\{860BB310-...}\Instance`, the
  DirectShow video-capture-device category). `cv2.VideoCapture(i)` (no explicit backend —
  what the production code actually calls) opens real frames at indices 0 and 2 on this
  machine; the `cv2.CAP_DSHOW` backend is not usable for by-index capture on this OpenCV
  build (raises immediately), so device *names* could not be confirmed that way.
- Right after connecting, both indices briefly showed solid placeholder colors (DroidCam's
  own "waiting" screen) even though the DroidCam app process was already running — a
  single instant `cap.read()` isn't enough; a short warm-up (~1.5 s + several reads) was
  needed before real video appeared. Once warmed up, index 0 showed a real live picture —
  confirmed by eye (it showed this machine's own terminal window and the Acer logo on the
  bezel, i.e. the phone was pointed at the laptop screen at the time, not at a person).
- With the backend restarted on that confirmed-live index 0, perception logged
  `track 1: face 324 px recognized in 289 ms` — a real face was detected and recognized,
  not a placeholder. `CAMERA_INDEX=0` is correct and stays pinned in `.env`.
- Camera still only gives 640x480 even though `.env` asks for 1280x720 — not yet checked
  whether a face is large enough (`MIN_FACE_PX=80`) at real kiosk standing distance; there
  is no higher-resolution fallback with this phone-as-camera setup if it isn't.
- The phone was pointed at the laptop screen during this test, not the kiosk spot — it
  needs aiming at the actual standing position before T1 is run for real.
- Using the phone as the camera (DroidCam over USB) works, but needs the phone screen on
  and the DroidCam app foregrounded for the whole session — a real risk across a 3-hour
  pilot if a call, a notification, or the screen locking interrupts it. Worth getting a
  dedicated USB webcam if one is available in time.

## Speed
`[perception]` lines (recorded before the black-frame problem above was caught, so these
numbers are real loop throughput but were measured against empty video — re-measure
against the now-confirmed-live camera before trusting them for the pilot):
- `0.0 fps, detection 87908 ms a frame, 2606 camera frames skipped (last 94 s)` — one-time
  stall: first-ever detection call downloads + loads `buffalo_l` (not steady-state).
- `12.7 fps, detection 74 ms a frame, 520 camera frames skipped (last 30 s)`
- `12.9 fps, detection 73 ms a frame, 512 camera frames skipped (last 30 s)`
- `12.4 fps, detection 77 ms a frame, 528 camera frames skipped (last 30 s)`

Tap-to-verdict timing (T10) not measured — needs the physical reader and a real session.

## Problems
- **Fixed** (`backend/cameras.py`): `os.uname()` crashed on Windows — only macOS and
  Linux branches existed. Added a `_windows_cameras()` path using
  `Get-PnpDevice -Class Camera -Status OK` (same passive "ask the OS" approach as the
  existing mac/linux code) and branched on `os.name == "nt"` before the `os.uname()`
  call. macOS/Linux code paths are untouched. `pytest tests -q` still 497 passed / 11
  skipped after the change. Committed as `1c512e0`.
- **Not fixed, and worse than first thought**: the Windows camera check reported "no
  cameras reported by the OS" all night, on every machine state tested (no camera, one
  camera, two cameras including a confirmed-live one). `Get-PnpDevice -Class Camera`
  apparently doesn't cover whatever class these devices register under — DroidCam's
  driver showed up under PnP class `MEDIA`, not `Camera`, when checked directly
  (`Get-PnpDevice -Status OK | Where FriendlyName -match camera` found
  "DroidCam Source 3" under `MEDIA`, alongside unrelated audio devices). The `_windows_cameras()`
  fix from earlier tonight does not actually solve camera detection on Windows — it only
  stops the crash. `pick_index()`'s default-to-0 fallback happened to land on the right
  index both times tested, but that is luck, not a working detector. Needs a real fix
  (probably reading the DirectShow registry category directly, like the "Camera —
  corrected finding" section above did by hand) before `python -m backend.cameras` can be
  trusted on Windows. Not attempted tonight — ran out of time before the laptop had to be
  packed up.
- Liveness model wasn't downloaded by Section 1's manual command list (see above) — fixed
  by running `python -m backend.fetch_liveness_models` by hand; both
  `2.7_80x80_MiniFASNetV2.onnx` and `4_0_0_80x80_MiniFASNetV1SE.onnx` are now present
  under `backend/models/anti_spoof`. The "`[liveness] assess failed, failing open: ...`"
  message is gone after restarting the backend; not yet confirmed a real liveness score
  prints, since no face crossed the camera again before shutdown.
- `backend/ports.py` was checked for the same Windows risk and is fine as-is —
  `pyserial`'s `comports()` and `glob.glob()` both degrade gracefully on Windows. It found
  the Arduino correctly once connected: `COM4, likely board, Arduino Uno (COM4), 2341:0043`.
- `git push` could not be completed from this session either — Git Credential Manager's
  auth prompt has the same can't-render-from-a-non-interactive-session problem as the UAC
  prompts. One commit (`1c512e0`, the camera fix + the first version of this file) is
  local-only as of shutdown; push it by hand.

## State at shutdown (18 Nov, laptop being packed into its case)
- Backend, serial reader and Postgres were all running and healthy right before shutdown:
  health `{"status":"ok","db":true}`, reader `listening on COM4 @ 9600`, camera confirmed
  live at index 0, liveness model present.
- Nothing was torn down cleanly — the laptop is simply being powered off. On next boot:
  `docker compose up -d db`, then Section 3's two commands again (backend + reader), after
  reconnecting the Arduino and re-pairing DroidCam (USB, both ends) — neither survives a
  reboot/unplug on its own.

## Still needed before this machine is pilot-ready
1. **Push `1c512e0`** (git push, by hand — the auth prompt needs a real interactive
   session).
2. **Fix Windows camera detection for real** (see Problems) — or accept `CAMERA_INDEX=0`
   pinned by hand each time, which is fragile if the device list ever changes.
3. **Point the phone at the actual kiosk spot**, not the laptop screen, then run T1–T10
   and liveness calibration (`pilot-macbook.md` sections 4–5) for real — the fps numbers
   above are not trustworthy evidence since they were measured against a different
   (blank) feed.
4. Check face size at real standing distance (640x480 cap, `MIN_FACE_PX=80`) — T4-
   equivalent.
5. Confirm a liveness score actually prints now that the model is present (no face was in
   view to test this before shutdown).
6. Cabucos to fill in `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD` in `.env` directly, then
   confirm a guardian email actually sends (not yet tested on this machine).
7. Decide whether the phone-as-camera setup is reliable enough for a real 3-hour pilot, or
   whether a dedicated USB webcam is worth sourcing before Thursday.
8. Set `OPERATOR_TOKEN` before the real pilot — the API and camera stream are wide open
   right now (dev mode).

---

## Session 2 (same day, laptop brought back after packing)

### Reconnect procedure (confirmed — nothing survives a reboot/unplug)
On relaunch: Docker engine was down (`docker ps` failed until Docker Desktop was
relaunched and given ~1-2 min), Arduino showed no port until physically replugged, and
DroidCam needed both ends reopened and reconnected (USB mode) again. All three came back
cleanly once redone — `docker compose up -d db`, replug the board, reopen DroidCam
app+client, then Section 3's two commands.

### Camera reconfirmed live (not a repeat of the black-frame mistake)
Learned from the first pass: before trusting the camera again, grabbed real frames with a
~1.5 s warm-up via `cv2.VideoCapture` and looked at them directly rather than trusting fps
numbers alone. Second attempt (after actually opening DroidCam on both the phone and PC,
not just plugging in the cable) showed a real photo of a person — camera confirmed
genuinely live this time, not a placeholder.

### Dashboard login — not a real gate
`http://localhost:8001/app/` showed "Operator Login, enter operator token" even though
`OPERATOR_TOKEN` is unset server-side. This is a **frontend-only quirk**, not a security
feature: `Dashboard.tsx:70` sets `authed = !!getToken()` — it only checks whether
*something* is saved in the browser's `localStorage`, never whether the server actually
requires it. `require_operator()` server-side is a no-op when `OPERATOR_TOKEN` is blank,
so any non-empty string typed into that box gets you in. Not a bug worth fixing before the
pilot (it'll behave correctly once a real `OPERATOR_TOKEN` is set), just worth knowing so
nobody wastes time hunting for a token that doesn't exist yet.

### T1 confirmed working end-to-end
Register flow (Scan UID → capture face) completed for at least one test student;
`POST /api/enroll/card` and `/api/enroll/active` both 200 OK, no `tailgating` row while
Register was open (correct — matches the design). Two card UIDs were tapped for
enrollment tonight: `C392263A`, `CCF98E02`.

### Extensive live testing happened (102 scored taps total)
```
status        | count
--------------+------
tailgating    |   82
accepted      |   24
mismatch      |    8
unregistered  |    1
```
Liveness scores, 102 samples:
```
min=0.000  mean=0.757  max=1.000
0.0-0.1 | 16   0.1-0.2 | 1   0.2-0.3 | 1   0.3-0.4 | 0
0.4-0.5 | 2    0.5-0.6 | 3   0.6-0.7 | 3   0.7-0.8 | 7
0.8-0.9 | 9    0.9-1.0 | 60
```
Clean-ish bimodal split: a low cluster (mostly 0.0–0.1) and a dominant high cluster
(0.9–1.0), with a thin, mostly-empty gap around 0.1–0.4. **Suggested `LIVENESS_THRESHOLD`
≈ 0.3–0.4** — sits in the gap, below the live cluster's low tail, above the spoof
cluster. Not set yet; needs Cabucos's review (now possible by eye — see next section)
before committing to a number, per the pilot doc's own rule.

### The actual pre-pilot blocker, now with visual proof
```
status      | liveness_pass | count | avg_score
------------+----------------+-------+----------
accepted    | t              |    18 |    0.902
accepted    | f              |     6 |    0.101
tailgating  | t              |    64 |    0.926
tailgating  | f              |    14 |    0.075
```
**6 taps logged `accepted` despite a liveness score averaging 0.101** — almost certainly
printed-photo/replay spoof attempts that got through, because `LIVENESS_THRESHOLD` is
unset and an uncalibrated liveness verdict is advisory-only (by design — see
`matcher.py: resolve()`, "only a *calibrated* liveness verdict may reject a genuine
card+face match as spoof"). This is expected, documented behavior, not a bug — but it is
the single biggest reason this machine is not pilot-ready yet: **right now, a printed
photo held up to a tapped card gets counted as attendance.** Setting the threshold above
closes this.

### New feature: debug snapshot capture (`DEBUG_SAVE_SNAPSHOTS`)
Built on request, to let liveness calibration be reviewed by eye instead of numbers
alone. Scoped deliberately, since the README states this project otherwise **never**
writes a face photo to disk (children's biometric data, no DPIA yet):
- New env var `DEBUG_SAVE_SNAPSHOTS` (default `false`) — documented in `.env.example`.
  Off unless explicitly turned on; this session turned it on locally to test it, and it
  is now **on in this machine's `.env`**.
- When on, saves one annotated JPEG per `accepted`/`spoof`/`tailgating` outcome (the only
  ones with a face to show — a mismatch/no-face/unwatched tap has nothing to snapshot) to
  `backend/debug_snapshots/`, named `{attendance_logs.id}_{status}_{live/spoof+score}_
  {uid}.jpg` so a file matches straight back to its DB row by eye.
- `backend/debug_snapshots/` is gitignored — never committed, never in a backup/dump path.
- Implementation: `backend/main.py` — a new `perception.on_frame` sink
  (`_snapshot_frame_sink`) buffers the latest frame per track id (bounded, 64 entries);
  `_save_snapshot()` is called from `_write_outcome()` (the single `db.insert_log`
  chokepoint for every matcher outcome) when the flag is on. `pytest tests -q` still
  **497 passed, 11 skipped** after the change.
- **25 snapshots saved tonight**, in `backend/debug_snapshots/` on this machine — browse
  them directly (filenames are self-describing, e.g. `101_accepted_spoof0.00_
  D1BC19B1.jpg` is an obvious spoof that got waved through).
- **Before the real pilot: delete `backend/debug_snapshots/` and set
  `DEBUG_SAVE_SNAPSHOTS=false`** in `.env`. Cabucos is responsible for this cleanup — not
  automated. Do not run this flag on with real students' faces.

### State at shutdown (session 2)
Backend, serial reader and Postgres stopped cleanly this time (not just powered off).
Three commits now local-only, still need `git push` by hand:
`1c512e0`, `f69d331`, and tonight's (`backend/main.py` snapshot feature + `.gitignore` +
`.env.example`, about to be committed as this file is).

## Still needed before this machine is pilot-ready — updated
1. **Push all 3 commits** (`git push`, by hand).
2. **Review the 25 snapshot images**, then **set `LIVENESS_THRESHOLD`** (~0.3–0.4
   suggested) on the Settings page once Cabucos agrees — this is the actual blocker: spoof
   attempts are currently being counted as attendance.
3. **Turn `DEBUG_SAVE_SNAPSHOTS` back off and delete `backend/debug_snapshots/`** before
   any real student's face is in front of this camera.
4. Fix Windows camera detection for real (still just `CAMERA_INDEX=0` pinned by hand —
   see Problems above; unchanged this session).
5. Point the phone at the actual kiosk spot (not wherever it happened to be tonight) and
   re-run T2–T10 for real, now that T1, camera, and liveness are all confirmed live.
6. Check face size at real standing distance (640x480 cap, `MIN_FACE_PX=80`).
7. Fill in `SMTP_USER`, `SMTP_FROM`, `SMTP_PASSWORD` in `.env`; confirm guardian email
   actually sends.
8. Decide phone-as-camera vs. a dedicated USB webcam for a real 3-hour session.
9. Set `OPERATOR_TOKEN` before the real pilot.
