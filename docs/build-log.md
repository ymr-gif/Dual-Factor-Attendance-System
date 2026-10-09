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
in access logs, so `POST /api/stream-ticket` trades the token for a random ticket valid for 60
seconds and for the stream only (`frontend/src/useStreamUrl.ts`). The token is never accepted from
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

**Verification.** `make test` (132 tests, no database or camera). Against a throwaway Postgres 16
with the previous schema loaded first: the count rule, lateness, sessions, override, and a second
`init_db`. From a UTC+8 host against that UTC server: 9 of 9 clock checks, 0 of 9 with the
session forced to UTC. A real backend process with perception on and no camera: tap queued,
resolved `unverified`, review entry present, stream refused without a ticket and opened with one.
Not checked: a real camera, so the "camera was watching, nobody showed a face" path has only its
unit tests.

## Design-only stubs (not built)

**Adaptive/late-bind matcher** — documented in `docs/design-notes.md` §5a: resolve a tap the instant the match is certain (strong unambiguous face already buffered) instead of always waiting `ASSOC_WINDOW_SEC`; keep the timed batch resolve as fallback when ambiguous/crowded. Cons driven to ~zero via an early-bind margin (`top1−top2`) + singleton-context guard, so it's never worse than today's optimal batch — a strict latency win behind an `ADAPTIVE_BIND` off-switch. Matcher-only change when built.
