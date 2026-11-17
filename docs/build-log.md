# Build log — what each built step contains

Detailed record of every built step: files touched, env knobs, and verification status. The
original spec (Steps 1–9) is summarised first; Steps 10 and later follow in detail.

- **Constraints / failure modes:** `docs/design-notes.md`.
- **Test runbooks:** `docs/verification.md`, `docs/face-verification.md`, `docs/privacy.md`.

> **Read the relevant entry before modifying a built area.** After changing code, update the
> matching entry here, and the README "Limits and next steps" section if the change affects what
> is unfinished.

---

## Original spec (Steps 1–9)

Moved here from the README's former "Status" checklist. Working rule at the time: no face or
liveness work started until tap, log and notify ran end to end.

- RC522 reads the UID; the Arduino is relay only (no on-device whitelist).
- Serial to FastAPI `/tap` to Postgres logging.
- Notify stub (console print) fires on every tap, registered or not.
- End-to-end test loop with a fake student (`S001`).
- 24/7 hardening: systemd services with auto-restart, persistent Postgres volume, serial
  reconnect, failed-tap retry queue.
- Step 6, face match (1:1): InsightFace `buffalo_l`, fail-open, best-of-N probe. Verified live
  2026-07-10 (genuine 0.86 / impostor 0.018). Runbook: `docs/face-verification.md`.
- Step 7, passive liveness (MiniFASNet): built and wired into `/tap` (`backend/liveness.py`,
  ensemble V2@2.7 + V1SE@4.0, fail-open). Warning: needs live threshold calibration before it is
  enforced.
- Step 8, guardian email: `backend/notify.py` emails the guardian when `SMTP_*` and
  `NOTIFY_EMAIL_ENABLED` are set; the console line always prints. Warning: not yet sent through a
  live provider.
- Step 9, 2FA enforcement: `backend/decision.py` collapses face and liveness into a per-tap
  `status`; `ENFORCE_2FA` turns a failed factor into `rejected`. Off by default.

## Foundation (Phase A)

**Step 10 (one-command setup) is built** — `docker-compose.yml` (db + backend), `backend/Dockerfile` (python:3.11-slim, fetches liveness weights at build), `Makefile` (`setup`/`up`/`down`/`dev`/`enroll`/…), `.dockerignore`, and `GET /health` (DB-reachability probe) in `backend/main.py`. Under compose the backend reaches Postgres as `host=db port=5432` (compose overrides `DB_DSN`). Warning: not yet run end-to-end on a clean checkout / GPU box.

**Step 11 (operator API + live tap stream) is built** — read endpoints `GET /api/attendance` (filters: date/status/student_id/limit, joined to student name, no embeddings), `GET /api/students` (roster + `enrolled` flag, no embeddings), `GET /api/stats/today` (counts by status), `GET /api/config` (active face/liveness/decision thresholds). Live stream: `backend/events.py` (thread-safe asyncio pub/sub; `/tap` is sync/threadpool so `publish()` uses `loop.call_soon_threadsafe`) + `WS /ws/taps`. `/tap` publishes each tap fail-open (broadcast error never breaks the response; `jsonable_encoder` handles the ts datetime). Auth: `OPERATOR_TOKEN` env + `require_operator` dep on all `/api/*` (Bearer or `X-Operator-Token`; unset = open dev mode, WS takes `?token=`). Verified live: all REST endpoints + a WS event on `/tap`.

**Step 12 (SPA scaffold) is built** — `frontend/` (Vite + React 18 + TS). `vite.config.ts` sets `base:/app/` and dev-proxies `/api`+`/ws`+`/health`→`:8001`. Router (`react-router-dom`): `/` (Dashboard) + `/kiosk`, `basename=import.meta.env.BASE_URL`. `src/api.ts` (typed `TapEvent`/`TapLog`/`Student`, token in localStorage → `X-Operator-Token`) + `useTapStream()` (auto-reconnecting WS hook, `?token=`). Backend serves the built SPA: `main.py` mounts `/app/assets` (StaticFiles) + `/app/{path}` catch-all falling back to `index.html`, **only if `frontend/dist/` exists** (backend still boots pre-build). `backend/Dockerfile` gained a `node:20-slim` web build stage → copies `dist` into the image. Makefile: `web-install`/`web-dev`/`web-build`. `frontend/node_modules` + `frontend/dist` gitignored; `package-lock.json` committed (Dockerfile `npm ci`). Dev at `localhost:5173/app/`. Verified: `web-build`→backend serves `/app` + SPA fallback + assets; Vite dev proxy reaches `/health` + `/api/config`. (`main.py`'s `/app/{path}` catch-all resolves via `os.path.realpath` and refuses anything escaping `frontend/dist/` — a path-traversal fix.)

**Step 13 (operator dashboard) is built** — pure frontend, no backend changes. Auth gate (token entry → `localStorage`, logout button). `TodayPanel` (counts + color-coded status pills from `GET /api/stats/today`, auto-refreshes on each live tap). `LiveFeed` (WS stream, newest 50 taps, status pills, face/liveness scores, red/amber row highlights for rejected/spoof/mismatch/flagged/tailgating/no_face, relative timestamps, WS connection pill). `HistoryTable` (`GET /api/attendance` with date picker + status dropdown + "Load more" pagination, 6-column table, empty/error/loading states). Layout: two-column grid (280px stats + fluid feed) above full-width history, stacks on mobile. `api.ts` gained typed `Config`, extended `Student` (consent/model/enrolled_at), `AuditEntry`, `ReviewItem` placeholders. Components: `frontend/src/components/{TodayPanel,LiveFeed,HistoryTable}.tsx`, `Dashboard.tsx` rewritten, `App.tsx` nav removed (auth lives in Dashboard — **note: nav was added back in Step 14**), `index.css` gained status color utilities + `.dash-grid` + responsive breakpoint.

## Flow track — perception + matcher (Phase B)

**Step 30 (perception service — Flow track keystone) is built** — `backend/perception.py`: one long-running camera-owner loop, detect → track → recognize *continuously* (cost per-track, not per-frame). `FaceTracker` does greedy-IoU association (`TRACK_IOU_THRESH`, `TRACK_MAX_MISSES`) → stable integer track IDs; recognition (`face.embed`) runs **once per new track**, the first frame it clears `MIN_FACE_PX`. Two in-process fan-out streams via `on_frame`/`on_face` sinks: **frame events** (`{track_id,bbox,recognized}` — box geometry only, safe for the boxes-only viewer, Step 35) and **face events** (`{track_id,bbox,embedding,live_score,ts}` — the 512-d embedding is PII, so delivered to in-process sinks only, **deliberately NOT the `/ws/taps` bus**; intentional deviation from the roadmap's "on the bus" wording, for the matcher, Step 31). `run(frames,...)` is decoupled from the camera so it consumes any frame iterable (video file / synthetic sequence). Camera ownership extracted into `face.open_capture(source)` (int index / numeric str / device path / video file) — perception is the **single camera owner** (design-notes §3); `capture_probe()` now routes through it. **Fail-open / single-owner**: `PERCEPTION_ENABLED` (code default **false**; the backend unit sets it **true**) — when true, `/tap` no longer opens the camera and logs card-only `unverified` (never silent `present`; design-notes §4 camera-dead) until the matcher (Step 31) correlates taps↔faces. Env: `PERCEPTION_ENABLED`, `PERCEPTION_SOURCE`, `TRACK_IOU_THRESH`, `TRACK_MAX_MISSES`, `PERCEPTION_FPS`; state surfaced in `GET /api/config`. Run offline: `PERCEPTION_SOURCE=clip.mp4 python -m backend.perception`. Verified with a deterministic synthetic image sequence (stable IDs across drift + track age-out, once-per-track recognition, both streams, no PII in the boxes stream). Warning: live-cam/video + GPU throughput acceptance deferred (`[GPU/HW]`). Perception `on_face` events also carry `is_live` (matcher spoof rule).

**Step 31 (tap↔face matcher) is built** — `backend/matcher.py` `Matcher` class: async correlation of buffered taps ↔ recognized faces. `/tap` (in `main.py`) branches on `perception.enabled()`: unknown card → sync `unregistered`; enrolled-but-no-reference → sync `unverified` (fail-open); enrolled → `matcher.add_tap(uid, student_id, reference_embedding, student)` and **acks immediately** (`{"status":"queued"|"debounced"}`) — the verdict is written later. A background resolve loop (`asyncio.to_thread(matcher.resolve)` every `RESOLVE_INTERVAL_SEC`) plus `perception.on_face(matcher.on_face)` + a daemon camera thread are started in the `_start_perception` startup hook when perception is on. `resolve(now)`: takes taps whose `ASSOC_WINDOW_SEC` window has closed, builds a cost matrix (`1 - cosine`, time-invalid pairs = sentinel), runs **Hungarian** (`scipy.optimize.linear_sum_assignment`), then per tap: assigned+≥`MATCH_THRESHOLD` → `accepted` (or `spoof` if `is_live` False **and** liveness calibrated — see the success/method fix below); assigned+below → `mismatch`; unassigned → `no_face`. Every assigned face is consumed; genuinely unassigned ripe faces → `tailgating` (cardless 1:N `db.search_face` pgvector nearest to name them, else "unknown", `uid=""`). Tailgating is deferred while any pending tap could still claim the face. `TAP_COOLDOWN_SEC` debounces held/duplicate cards per uid; face buffer is bounded (`MAX_FACE_BUFFER`, drop-oldest). `decision.py` statuses `no_face`/`mismatch`/`spoof`/`tailgating` (all review states — `counts_as_present` excludes them + `rejected`; `accepted`/`flagged`/`unverified`/`unregistered` keep prior fail-open behavior). Matcher is **decoupled for tests** (injected `outcome_sink`, `face_search`, `clock`); `main._write_outcome` does log→notify→broadcast. Env: `ASSOC_WINDOW_SEC`(4), `TAP_COOLDOWN_SEC`(2), `MATCH_THRESHOLD`(=FACE_THRESHOLD), `TAILGATE_NAME_THRESHOLD`, `RESOLVE_INTERVAL_SEC`(0.5), `MAX_FACE_BUFFER`(256). Verified: edge-case unit assertions (accepted/mismatch/no_face/tailgating/spoof, more-taps-than-faces, more-faces-than-taps, Hungarian cross-order, cooldown, deferred window) + live run. Deps: `scipy` (Hungarian).

**Step 33 (identity & matching) is built** — **(part)** `backend/enroll.py` `--capture` bug fixed (uses `probe.embedding`, was treating the `Probe(frame,bbox,embedding)` tuple as an embedding). Shared enroll core extracted (`embeddings_from_frames`, `average_reference`, `enroll_student`) — I/O-free of the CLI, reused by the register wizard (Step 35). **(rest)** HNSW ANN index `students_face_embedding_hnsw` (cosine ops) in `schema.sql`; cardless 1:N via `db.search_face` (matcher) + `POST /api/search-face` (multipart image upload → encode → nearest, no image stored; needs `python-multipart`); duplicate-enroll detection `db.find_duplicate` in `enroll_student` (warns at `DUP_ENROLL_THRESHOLD`, default FACE_THRESHOLD; doesn't block; noted in audit) — `enroll_student` returns `{"used","duplicate"}`; re-enroll reminders `db.stale_enrollments` + `GET /api/reenroll-due` (flags refs older than `REENROLL_AFTER_DAYS` or non-current `embed_model`). Env: `DUP_ENROLL_THRESHOLD`, `REENROLL_AFTER_DAYS`. Note: the pre-existing S001 row shows as reenroll-due (`embed_model` NULL — enrolled before provenance tracking).

## Data model & responsibility (Phase C)

**Step 20 (privacy/compliance) is built** — plus the Phase B **schema pass** (idempotent ALTERs in `schema.sql`: `students.embed_model`/`enrolled_at`/`face_consent`/`face_consent_at`, new `audit_log` + `review_queue` tables — `review_queue` is a Step 34 skeleton). `backend/privacy.py` holds policy: **consent gate** `FACE_CONSENT_REQUIRED` (default **false** = back-compat; when true, enroll refuses + `/tap` skips face/liveness for un-consented students → NFC-only `unverified`), **retention** `ATTENDANCE_RETENTION_DAYS`/`SCORE_RETENTION_DAYS` (0 = forever) applied by `privacy.purge()` via `make purge` / `python -m backend.privacy`. `db.py`: `get_student`, `set_consent`, `insert_audit`/`get_audit`, `delete_student` (erasure: logs + roster row), `purge_old_logs`, `null_old_scores`; `set_face_embedding` now writes `embed_model`+`enrolled_at`. `main.py` endpoints (all `require_operator`): `POST /api/students/{id}/consent`, `DELETE /api/students/{id}` (right-to-erasure), `GET /api/audit`; audit actor from optional `X-Operator-Actor` header; `/api/config` gained a `privacy` block; both `/tap` paths gate on `privacy.consent_ok`. `enroll.py`: `--consent` flag, consent enforced in `enroll_student`, writes model provenance + an `enroll` audit entry. Encryption-at-rest is a documented deferred 2nd pass. Docs: `docs/privacy.md` + `docs/verification.md` (runbook to test Steps 10–33).

**Step 21 (attendance sessions + guardian digest) is built** — `backend/schema.sql` gains `attendance_sessions` view (pairs consecutive taps per student per day into check-in/check-out sessions; lone odd tap = check_out NULL). `db.py`: `LATE_CUTOFF` env (HH:MM), `get_sessions()`, `get_summary(date)` (expected/present/absent/late per enrolled roster), `get_attendance_csv()`. `main.py`: `GET /api/attendance/summary?date=`, `GET /api/attendance/sessions`, `GET /api/attendance.csv`. `backend/digest.py`: one-shot CLI (`python -m backend.digest [--date YYYY-MM-DD] [--dry-run]`) queries sessions per student, sends batched guardian summary via `notify._send()`. Covers absent students (no sessions → skipped, logged). `Makefile`: `digest` target. `.env.example`: `LATE_CUTOFF=08:00`.

**Backend management layer (Steps 14/22/34/50 merged) is built** — additive-only, no existing pipeline touched. `db.py` gained `insert_student`, `update_student`, `insert_review`, `get_review_queue`, `resolve_review`, `get_setting`, `set_setting`, `get_all_settings`. `main.py` gained `POST /api/students`, `PATCH /api/students/{id}`, `POST /api/students/{id}/enroll` (multipart frame upload → encode → average → store), `GET /api/review`, `POST /api/review/{id}/resolve`, `GET /api/settings`, `PUT /api/settings`, `GET /metrics` (Prometheus). `backend/settings.py`: typed runtime settings layer (DB > env > default, tunable keys whitelist). `backend/doctor.py`: standalone health check (`make doctor`, `python -m backend.doctor`). `schema.sql`: `settings` table. All verified live; regression: `/tap`, `/health`, `/api/attendance`, WS all pass.

## UI surfaces (Phase E)

**Step 14 (roster + browser enrollment) is built** — `frontend/src/pages/Roster.tsx`: student table with inline add/edit/delete, consent checkbox toggle. `frontend/src/pages/Register.tsx`: student dropdown (create-new inline), live webcam capture (`getUserMedia`), 3–5 shot thumbnails, FormData upload → enroll endpoint, per-frame result + duplicate warning. `frontend/src/pages/Settings.tsx`: editable tunable runtime settings via `GET/PUT /api/settings`. `frontend/src/App.tsx`: nav bar added (Dashboard/Roster/Register/Review/Settings/Kiosk), management links hidden when unauthenticated, listens for `auth-changed` events. `frontend/src/index.css`: `.nav`, `.page`, `.card`, `.btn` utilities.

**Step 15 (kiosk verdict screen) is built** — `frontend/src/pages/Kiosk.tsx` rewritten: fullscreen color-coded verdict (green/amber/red backgrounds), large status icon + student name, 5s auto-reset to idle, connection indicator. Audio cues via Web Audio API (accept chime + reject buzz), mute toggle, armed after first user gesture.

**Step 34 (manual review queue) is built** — `frontend/src/pages/Review.tsx`: unresolved review table with Confirm/Override/Dismiss per row, confirmation dialog. Backend endpoints `GET /api/review` + `POST /api/review/{id}/resolve` (from management layer).

**UI surfaces (Tasks 1–9) are built** — pure frontend over existing endpoints: public boxes-only `Viewer`, attendance `Summary`/`Sessions`/CSV export, `Audit`/`Reenroll`/`Lookup` panels, `Ops`/health readout, kiosk audio. Pages in `frontend/src/pages/`, wired in `App.tsx` (operator pages behind `authed`; Viewer + Kiosk public). `api.ts` gained `reqBlob`/`reqText` + the per-task fetchers. Task 10 (README screenshots / final polish) deferred to Step 16.

## Camera stream + Register hardening (recent)

**MJPEG camera stream (precursor to Step 35) is built** — `GET /stream.mjpeg` in `main.py`. Perception's `on_frame` sink delivers annotated frames (green/amber boxes + track IDs). `CameraFeed.tsx` renders the stream on the dashboard via `<img src="/stream.mjpeg">`. `PERCEPTION_ENABLED` default flipped to **true** in the unit — camera runs at boot. `_emit` signature changed to `_emit(sinks, *args)` so frame sinks receive `(frame, event_dict)`. **Per-client fan-out (fixed):** `_on_frame_event` broadcasts each JPEG to a **set of per-client queues** (`_mjpeg_subscribers`, one bounded `maxsize=2` `asyncio.Queue` per connected viewer) via `_broadcast_frame` on the loop thread; the endpoint registers its queue on connect and `discard`s it in a `finally`. Previously a single shared queue meant concurrent viewers stole frames from each other — now Dashboard + public Viewer + Register capture-fallback can all watch at once (verified: 3 concurrent clients each got the full 47 frames/5s, not a 3-way split). Slow clients drop their own oldest frame; no viewers = fan-out skipped.

**Register camera-conflict fallback (fixed)** — `frontend/src/pages/Register.tsx`: browser `getUserMedia` fails when perception (single camera owner) holds `/dev/video0` ("Starting videoinput failed"). Register falls back to capturing enrollment frames from `<img src="/stream.mjpeg">` (`camSource: 'user'|'stream'`), drawing whichever source is live to the canvas; shows a warning note that stream frames carry detection boxes. Alternative for box-free frames: `PERCEPTION_ENABLED=false`, restart, enroll via `getUserMedia`, re-enable.

**Register guided capture + live quality gate is built** — backend `GET /api/perception/state` (`require_operator`) returns a live camera-quality snapshot computed **inside `_on_frame_event`** from perception's own per-frame detections (`_perception_state` global; no extra camera open, no image stored): `{enabled, ready, reason, n_faces, face_px, brightness, min_face_px, age}`. Gate reasons (server-side): perception off → soft/unavailable; stale (age>2s); `No face detected`; `N people in frame — only one at a time`; `Move closer` (< `MIN_FACE_PX`); `Not enough light` / `Too bright / backlit` (face-region mean vs `REGISTER_BRIGHT_LOW`/`REGISTER_BRIGHT_HIGH`); `Center yourself` (bbox center offset vs `REGISTER_CENTER_MAX`); else `Ready`. `Register.tsx` polls it every 700ms, shows a green/amber status pill, and **disables Capture when `enabled && !ready`** (soft/no-block when perception is off). Camera box shows during create+enroll. **Scan-to-fill UID**: a "Scan UID" button arms `useTapStream`; the next tapped card fills the UID field (`e.log.uid`), 20s auto-cancel — this logs an `unregistered`/tailgating tap for the blank card (auditable, harmless). Student ID stays free-text. Env: `REGISTER_BRIGHT_LOW`(55), `REGISTER_BRIGHT_HIGH`(215), `REGISTER_CENTER_MAX`(0.45). Verified live (empty scene → `No face detected`, brightness 102, age 0.1s). Angle/pose beyond centering is a future refinement (frame events carry bbox only, not keypoints).

**Success status + method labelling + uncalibrated-liveness fix (built)** — the "fully verified" role is `accepted` (green pill, `reason="verified"`). (1) **`method` reflects the factors used** — matcher outcomes with a card **and** a compared face write `method="nfc+face"` (`_present`/`_spoof`/`_mismatch`); cardless faces stay `face` (tailgating); card-only paths (`no_face`/`unregistered`/`unverified`) stay `nfc`. `LiveFeed.tsx` shows a method chip. (2) **Uncalibrated liveness no longer rejects genuine matches as `spoof`** — the matcher's spoof branch is gated on `liveness.calibrated()` (`LIVENESS_THRESHOLD` set). Until calibrated, the argmax liveness verdict is **advisory**: a matched card+face resolves to `accepted` (score still logged for later calibration) instead of `spoof`. (This is why a live person scoring face 0.51/0.72 with live 0.02 was mislabelled `spoof`; now `accepted | nfc+face`.) Setting `LIVENESS_THRESHOLD` reactivates real spoof-blocking. Verified deterministically (uncalibrated+not-live→accepted; calibrated+not-live→spoof; calibrated+live→accepted; all `nfc+face`). **Open follow-up (track churn):** one person can spawn multiple short-lived tracks → the matched face consumes its tap while leftover phantom tracks of the same person surface as extra `tailgating` rows; a held card read past `TAP_COOLDOWN_SEC` doubles the tap. Tune `TRACK_MAX_MISSES`/`TRACK_IOU_THRESH` + cooldown.

## Status wiring, stream access, attendance clock (10 Oct 2026)

Four things that were built earlier but not connected, plus one bug found while checking them.
Earlier entries in this file still describe the old behaviour; where they disagree, this one wins.

**The per-tap status now decides attendance.** `decision.counts_as_present()` had no callers, so
`db.get_summary`, `db._is_late` and the `attendance_sessions` view counted every tap of a known
card: a `rejected`, `mismatch`, `spoof`, `no_face` or `tailgating` tap still marked the student
present. All three now share one SQL rule (`db._COUNTED_SQL`; the view spells the same list out,
and `tests/test_decision.py` fails if the two drift). A tap counts when its status counts, or when
an operator resolved its review as `override`.

**The review queue is filled.** `db.insert_review` had no callers, so the Review page (Step 34)
was always empty. `main._queue_review` now adds every tap that failed a check
(`decision.needs_review`: `flagged`, `rejected`, `no_face`, `mismatch`, `spoof`, `tailgating`),
from the matcher's outcome writer and from the per-tap path. A failed insert is printed and the
tap still notifies and broadcasts.

**A camera that delivers nothing no longer reads as `no_face`.** Whether a card-only tap during
a camera outage should count at all is still an open decision (design-notes section 10, item 6);
what follows keeps the outcome such a tap had before, and makes it visible.
Before, a camera that delivered nothing made every queued tap `no_face`. With the count wired to
the status that would have marked the whole school absent. The matcher now takes a heartbeat:
`perception.on_frame` feeds `Matcher.note_frame`, and each pending tap counts the frames inside its
own association window (which reaches back, so a frame just before the tap counts too). No frame
at all means the tap was never watched: status `unverified` (counted), an `[ALERT]` line, and a
review entry even though `unverified` is otherwise not reviewed. The camera is judged over the
tap's window, not at resolve time. `Matcher(camera_heartbeat=False)`, the default used by tests
and offline runs, keeps the old behaviour.

**`ENFORCE_2FA` is unchanged**: read only when perception is off. With perception on, `mismatch`
and `spoof` never count regardless, and a camera outage still fails open.

**The camera stream needs the operator token.** `GET /stream.mjpeg` was open to anyone who could
reach the port, even with `OPERATOR_TOKEN` set. It is guarded by `main.require_stream_access`: the
token in a header, or a ticket. An `<img>` cannot send a header, and a credential in a URL ends up
in access logs, so `POST /api/stream-ticket` trades the token for a random ticket that opens the
stream only, once, within 30 seconds (`frontend/src/useStreamUrl.ts`). The token is never accepted from
the URL. `/ws/taps` still takes it as `?token=`; that is unchanged and still open to the same
objection. The Viewer page was called "public, boxes-only" above. It shows this stream and always
did, so with a token set it now needs the token.

**Attendance clock (bug fix).** Every "which day" and "what time" is computed in SQL
(`ts::date`, `ts::time`, `CURRENT_DATE`) in the session's time zone, and the Postgres container
runs on UTC. On a UTC+8 host a 07:30 tap was filed under the previous day and compared with
`LATE_CUTOFF` as 23:30, while `get_summary` took "today" from Python's local date. `db.get_conn`
now runs `SET TIME ZONE` on each session: `ATTENDANCE_TZ` if set, else the backend machine's zone
(the IANA name behind `/etc/localtime`, else the UTC offset). `get_summary` asks the database for
today. The Summary and History pages used `toISOString()`, the UTC date, as their default day;
they use the local date now. An unknown zone name is reported once and the session stays on UTC.
Stored timestamps are `timestamptz` and did not change; only how they are bucketed did.

**Verification.** `make test` (no database or camera). Against a throwaway Postgres 16
with the previous schema loaded first: the count rule, lateness, sessions, override, and a second
`init_db`. From a UTC+8 host against that UTC server: 9 of 9 clock checks, 0 of 9 with the
session forced to UTC. A real backend process with perception on and no camera: tap queued,
resolved `unverified`, review entry present, stream refused without a ticket and opened with one.
Not checked: a real camera, so the "camera was watching, nobody showed a face" path has only its
unit tests.

## Guardian notification, study build (16 Nov 2026)

One entry per change, in the order they were built. The IDs (PC-019 and so on) are the
research group's change queue.

**PC-019: guardian mobile, checked on save.** `students.guardian_mobile` (nullable). A number
is accepted as `09XXXXXXXXX` or `+639XXXXXXXXX`, with spaces, dashes, dots and brackets ignored,
and stored as `09XXXXXXXXX`, the form Semaphore's API documentation uses (`backend/contacts.py`).
Anything else is refused with 422 before the student is saved, on create and on update; the
message describes the format and does not repeat what was typed. The guardian email gets the
same treatment with a loose shape check. When a contact is saved, `notify.contact_test` sends
one message to it and the reply carries the outcome per channel (`contact_test`), also written
to `audit_log` as a `contact_test` row that holds the outcome and never the contact. Email: sent
when `NOTIFY_EMAIL_ENABLED` and `SMTP_HOST` are set, otherwise reported as skipped; a failed
send is reported and the student is still saved. SMS: always "SMS test skipped" for now, there
is no sender yet. An update tests only the contact that request sent. The Roster and Register
pages have the new field, and a refused save now shows the server's reason.

**Guardian contacts no longer leave the roster.** The `/tap` response and the live tap event
carried the whole student row minus the face template, so the guardian email went to the card
reader's reply and to the guard's screen. `main._public_student` drops `guardian_email` and
`guardian_mobile` as well. The Roster page (operator) still shows both.

Not built here: a blank field in an update leaves the stored contact as it was, so a contact
cannot be cleared from the Roster page yet.

**Verification.** `pytest tests` (221 passed; no database, camera or SMTP server). The schema
change and the three roster queries were run against a scratch Postgres database, twice through
`init_db`. `npm run build` passes. Not checked: a real SMTP send of the contact test.

**PC-022: only an entry that counts is sent.** `notify.notify` still prints the operator
console line for every tap, with the status and the warnings. A guardian message goes out only
when the card belongs to a student on the roster and the status is one that counts as
attendance: the gate reads `decision.not_counted_statuses()`, the same list the attendance
queries use, so the two cannot drift. Before this, every tap with a guardian email on file sent,
including "Attendance was DENIED".

**PC-023: what the message says.** One sentence, the same for SMS and email:
`<name> entered the Hua Siong College of Iloilo <entry point> on <Mon D, YYYY> at <H:MM AM/PM>.`
The SMS puts the sender name in front (`SEMAPHORE_SENDER`, default `SAFEHSCI`), so the default
text is the sample the sender name was applied for. `ENTRY_POINT` (default `main guardpost`)
names the place. The date and time are written in `ATTENDANCE_TZ`, or in the machine's own zone
when that is unset or unknown. The SMS is kept to 160 characters by shortening the name only:
first the given name and surname, then a cut ending in "..."; the date and time are never cut. A
student with no name on file is written as "Your student". The email no longer carries the
student ID, method, status, scores or warnings, and a failed send prints the kind of error, not
the exception text. `backend/digest.py` builds its own message now; the daily digest itself is
unchanged. Limit: the 160 count assumes plain GSM characters; a name with other characters
makes the provider send a shorter-part message. Nothing sends an SMS yet (PC-018).
`pytest tests`: 253 passed.

**PC-020: notification log.** New table `notification_log`, one row per entry and channel
(`UNIQUE (log_id, channel)`). Columns: `t0` (the entry's own `attendance_logs.ts`), `t1` (when
the mail server or the SMS provider accepted the message), `latency_ms`, `status`,
`provider_message_id`, `error`, `attempts`, `claimed_at`. Status is `PENDING`, `DELIVERED`,
`FAILED` or `DISABLED`. `t1` and the latency are stamped by Postgres (`clock_timestamp()`), so
`t0` and `t1` come from one clock. The row holds no student ID and no recipient, the error is
the kind of error only, and the row is deleted with its entry.

`notify.notify` writes the row before it sends. A channel that is off, has no SMTP host or has
no guardian contact on file gets a `DISABLED` row with the reason and sends nothing. Otherwise
the row is opened `PENDING`, claimed, the message is sent, and the row is closed `DELIVERED` or
`FAILED`. An entry that already has a row for the channel is not sent again, and when the row
cannot be written nothing is sent. SMS rows are `DISABLED` until the sender exists (PC-018).
The send still happens inside the tap (PC-021 moves it out).

`backend/notify_report.py` turns the rows into the study's numbers: per channel, for all
entries and for peak and off-peak, the counts by status, the delivery rate
(`DELIVERED / (DELIVERED + FAILED)`; `DISABLED` and `PENDING` left out) and the latency in
seconds (n, mean, sample SD, median, min, max over `DELIVERED` rows). Peak is `PEAK_START` to
`PEAK_END` on the school clock (default 07:00 to 07:30, end not included). Served by
`GET /api/notifications/summary` and `GET /api/notifications.csv`, both with optional
`date_from` and `date_to`. Limits: `DELIVERED` means the server accepted the message, not that
the guardian read it; an email that bounces later still counts as delivered.
`pytest tests`: 292 passed, 7 skipped. The 7 are `tests/test_notification_db.py`, which runs the
real statements and needs `TEST_DB_DSN` to name a scratch database; run that way, 7 passed.

**PC-044: erase leaves no trace of the student.** `DELETE /api/students/{id}` already removed
the roster row (with the face template and the guardian contacts) and the logs under the
student ID. It now also removes, in the same transaction: the taps the card made before it was
on the roster (logs with that UID and no student), the notification and review rows of all
those logs, the target and detail of every audit row about the student, the detail of an audit
row about someone else that names the student (the duplicate-face note `dup?~<id>@<score>`),
and a review reason that names the student (`nearest=<id>`). After the database,
`privacy.erase_student` drops the card's lines from the serial reader's failed-tap queue
(`FAILED_TAPS_QUEUE`), rewriting the file beside itself and swapping it in.

The audit row that records the erase has no target and holds counts only
(`logs=2 students=1 notifications=1 audit_rows=3`). It is written inside the erase
transaction, so there is no erase without its record. A new student's `create` row no longer
holds `uid=<card UID>`.

What the erase may touch is kept narrow, because the audit log is the thing an operator must
not be able to quietly edit. Audit rows are taken by exact target and only for the actions
that target a student, so erasing an ID spelled `review#12` does not reach a review row.
Text is scrubbed only in the three forms the code writes (`db.names_student`), not by a free
search, so a student whose ID is `TEST` or `3` takes only their own rows. An ID that is not on
the roster does nothing and returns 404, with one exception: an ID that an audit row about a
student still carries, which is what an erase by an older build left behind (its `erase` row
held the student ID). Running the erase again cleans those.

Limits. Not reached: backup files (`make backup`), a queue file kept on another machine, and
the operator console output. `queued_taps` is in the response and not in the audit row; it
comes back `null` when the queue file could not be rewritten, and the operator then has to
clean it by hand. Deleted rows stay in Postgres' own files until they are vacuumed; they are
in no query result and no dump. The path ID is matched as typed (create stores IDs in upper
case).
`pytest tests`: 325 passed, 8 skipped. With `TEST_DB_DSN` set the 8 run too, among them
`tests/test_erase.py::test_after_erase_a_dump_of_every_table_has_no_hit`, which erases one
student on a real Postgres, searches every row of every table for the student ID and the
card UID, and first checks that made-up IDs change no row.

**PC-021: guardian messages go out in the background, with retries, inside 60 s.** The tap
no longer waits for the mail server. `notify` writes the `PENDING` row and hands the message to
`backend/sender.py`, which only appends it to a list; one thread started in `on_startup`
sends it. A try that certainly did not go out (`sender.Retryable`: no connection, TLS or a
login that is not a flat refusal, or a 4xx "try later") is repeated after 2, 4, 8 and then
every 16 s. Anything else ends the message as `FAILED` at once: a 5xx refusal will not change,
and after a timeout or a dropped connection during the hand-over nobody knows whether the
message left, so a second try could send it twice. The deadline is 60 s after the entry
(`t0`); a try that would start at or after it is not made (`not sent within 60 s; last error:
...`), and each try gets only the seconds that are left (SMTP takes the smaller of that and
`SMTP_TIMEOUT`). An error from closing the connection after the server accepted the message
no longer turns a sent message into `FAILED`.

On start, `sender.recover` reads back the `PENDING` rows (`db.pending_notifications`). A row
that was never claimed and is younger than 60 s is queued again with its own deadline; a
claimed row is `FAILED` as `interrupted during send` (it may have left); an older row is
`FAILED`; a row whose channel is now off or whose contact is gone is `FAILED`.

Limits. One thread, so messages go one at a time: a server that is slow to answer holds
back the ones behind it, and they fail at their own deadlines. A row whose result could not
be written (the database went away mid-send) stays `PENDING` and claimed until the next start
fails it. `DELIVERED` still means the server accepted the message.
`pytest tests`: 363 passed, 9 skipped (new `tests/test_sender.py`: queueing, backoff
schedule, deadline, time per try, which SMTP errors are retried, restart cases, the thread).
With `TEST_DB_DSN` set, `tests/test_notification_db.py` also reads pending rows back from a
real Postgres.

**PC-018: guardian SMS through Semaphore, off by default.** The `sms` channel now sends:
`notify._send_sms` posts the entry SMS (`sms_text`, PC-023) to Semaphore's
`/api/v4/messages` with the key, the number, the text and the sender name in the request
body, and stores the returned message ID on the `DELIVERED` row. It goes through the PC-021
sender, so the tap does not wait. Retried only when Semaphore certainly did not take the
message: no connection, `429` or `503`. A read timeout, a dropped connection, another `5xx`,
a `4xx`, a reply that is not a message list, or a message Semaphore marks `Failed` ends the
row as `FAILED` with the HTTP status only. Saving a guardian mobile sends one check SMS and
records `SMS test sent` or `SMS test failed: SmsRefused <status>`.

Off unless `NOTIFY_SMS_ENABLED=true` and `SEMAPHORE_API_KEY` is set; otherwise the row is
`DISABLED` with the reason. Not tried against the live API: Semaphore has no sender name for
this account yet (`SAFEHSCI` waits on the telcos), and a live send costs credits. Every test
replaces `requests.post`; the test fixtures switch SMS off so no other test can reach it.
Limits: Semaphore's `Pending` status means queued, not delivered to the handset; a later
`Failed` is not read back.
`pytest tests`: 391 passed, 9 skipped (new `tests/test_sms.py`).

**PC-027: both factors required.** `unverified` (the face could not be checked: camera down,
no reference, no consent) no longer counts as present: it is in `decision._NOT_PRESENT`, in the
`attendance_sessions` view's list and so in every attendance query, and the guardian is sent
nothing. It now goes to the review queue with the reason (`face not checked`,
`no face reference`, `no face consent`, or the camera alert), where an operator override counts
it. This settles open question 6 in `docs/design-notes.md` as option (b). Not changed:
`docs/operations.md` still says `unverified` counts; that file has edits in progress that are
not part of this build.
`pytest tests`: 391 passed, 9 skipped.

**PC-031: a face with no tap is named by the guard, not the system.** The matcher is built
without the one-to-many search (`FACE_SEARCH_ENABLED`, default false), so a face that no tap
claims is logged `tailgating` with no student and the reason `face with no tap`, and the live
feed highlights it as before. On the Review page such a row has a roster picker: the guard
picks the student (`identified`) or dismisses it. The pick is stored on the review row
(`review_queue.identified_as`, a foreign key to the roster with `ON DELETE SET NULL`, so an
erase clears it) next to `resolved_by` and `resolved_at`; the audit row holds the word
`identified` only. Only a `tailgating` row takes a pick, and the pick must be on the roster.
`/api/search-face` (the Lookup page) answers 403 while the search is off.
Not built: a grace window before a face is flagged (today it follows `ASSOC_WINDOW_SEC`, 4 s;
Cabucos floated 60 s, untested and not in the paper). Not checked: how many alerts a stream of
non-enrolled passers-by raises at the gate.
`pytest tests`: 403 passed, 10 skipped. With `TEST_DB_DSN` the real-database test checks the
foreign key, the tailgating-only rule and the erase.

**Camera size setting.** `CAMERA_WIDTH` and `CAMERA_HEIGHT` ask a live camera (an index or
a `/dev/` path, never a video file) for a capture size in `face.open_capture`, which both the
tap capture and the perception service use. Unset, nothing is asked and the driver's default
stays, as before. A size the camera does not give is printed with the one it gives. Not tried
on the A4tech or the MacBook Air yet; the size to use is for the dry run to settle (PC-045).
`pytest tests`: 409 passed, 10 skipped (new `tests/test_camera_size.py`).

**Two-factor switch on the Settings page.** `decision.enforcing()` now reads `enforce_2fa`
from the `settings` table on every decision, so the key the Settings page could already save
takes effect; before this, only `ENFORCE_2FA` was read and a saved value did nothing. Nothing
saved, or the table unreadable, falls back to `ENFORCE_2FA` (default false). The page has an
ON/OFF switch at the top and notes that with the camera pipeline on, a wrong face or a spoof
never counts either way. Switch keys (`enforce_2fa`, `use_gpu`, `face_consent_required`)
take only `true` or `false`. Every settings change is now written to the audit log. The
tests get an in-memory settings table (autouse), so no test reads the real one.
`pytest tests`: 414 passed, 10 skipped (new `tests/test_enforce_switch.py`).

**PC-033: camera-down label.** A tap the camera gave no frame for keeps its handling
(`unverified`, not counted, queued for review, `[ALERT]` in the log) and now carries the
reason `student scans and enters, camera down -- cannot verify face`, shown on the Review
page and the live feed. Only the perception path can tell a dead camera from an empty frame;
the direct path keeps `face not checked`. `pytest tests`: 414 passed, 10 skipped.

**Camera reopened after an outage (PC-033).** Before, the camera loop ran once: after
`CAMERA_MAX_MISSES` failed reads (600, about 60 s) it stopped for good, and a camera
unplugged for longer needed a backend restart. `perception.run_forever()` now owns the
camera thread: when a live camera (unset, an index, or a `/dev/` path) stops or is missing,
it reopens it every `CAMERA_RETRY_SEC` (5 s), re-resolving which camera to use, and says so
once per outage. A pipeline error no longer ends the thread. A video file still runs once.
`CAMERA_MAX_MISSES` default lowered to 100 (about 10 s) since giving up is no longer final.
A `/dev/` path now counts as a live camera here too (it already did for the capture size).
Not tried on the A4tech or the Mac yet: dry-run B21. Not covered: a read that hangs instead
of failing. `pytest tests`: 418 passed, 10 skipped (new `tests/test_camera_reopen.py`).

## Design-only stubs (not built)

**Adaptive/late-bind matcher** — documented in `docs/design-notes.md` §5a: resolve a tap the instant the match is certain (strong unambiguous face already buffered) instead of always waiting `ASSOC_WINDOW_SEC`; keep the timed batch resolve as fallback when ambiguous/crowded. Cons driven to ~zero via an early-bind margin (`top1−top2`) + singleton-context guard, so it's never worse than today's optimal batch — a strict latency win behind an `ADAPTIVE_BIND` off-switch. Matcher-only change when built.
