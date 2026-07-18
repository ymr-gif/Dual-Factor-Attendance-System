# nfc-scan — build roadmap (Steps 10–16)

Handoff / build list for the user-friendliness work. **Do the phases in order** — each
depends on the ones above it. Steps 1–9 (NFC → log → face → liveness → notify → 2FA) are
done; see README "Status" and CLAUDE.md "Build order". This doc picks up at Step 10.

## How to use this doc
- One phase at a time, top to bottom. Don't start a phase until its **Depends on** is met.
- A phase is done only when its **Acceptance** check passes. Then tick its box in the summary.
- Keep the two conventions the codebase already follows:
  - **Fail-open**: nothing new (WebSocket down, dashboard offline) may break `/tap` logging.
  - **Env-driven config**: every knob goes in `.env.example`; no secrets in code.
- After each phase: update README "Status", CLAUDE.md build order, and `.env.example`.

## Locked tech decisions
- **Frontend**: Full SPA — **Vite + React + TypeScript**. Single app, two routes:
  `/` (operator dashboard, auth-gated) and `/kiosk` (fullscreen tap feedback).
- **Live updates**: **WebSocket** (`/ws/taps`) — FastAPI native; backend broadcasts each tap.
- **Serving**: dev = Vite dev server proxying `/api` + `/ws` to `:8001`. prod = `npm run build`
  → `frontend/dist` mounted by FastAPI `StaticFiles`. No separate web server.
- **Operator auth**: single shared `OPERATOR_TOKEN` (env) checked by a FastAPI dependency.
  Kiosk route is unauthenticated (LAN kiosk); WS takes the token as a query param for `/`.
- **Packaging**: `docker-compose` (backend + Postgres) + a `Makefile` wrapping common commands.

> **Note**: the **Flow track (Steps 30–35)** below evolves this system into a continuous
> multi-student guardpost and **supersedes parts of this UI track** — Step 14 (browser enroll)
> → register wizard (Step 35), Step 15 (kiosk) → boxes-only viewer (Step 35), Step 16 roles
> → roles (Step 35). Steps 11 and 12 are shared prerequisites. Read Track 30–35 before starting
> 13–16 so those concepts are built once, there.

## Progress summary
- [ ] Step 10 — One-command setup (foundation)
- [ ] Step 11 — Backend API expansion + live tap stream  *(prereq for Flow track)*
- [ ] Step 12 — Frontend scaffold (SPA toolchain)  *(prereq for Flow track)*
- [ ] Step 13 — Operator dashboard (read views)
- [ ] Step 14 — Roster + browser enrollment  → *see Step 35 (register wizard)*
- [ ] Step 15 — Kiosk feedback screen  → *superseded by Step 35 (boxes-only viewer)*
- [ ] Step 16 — Hardening & polish  → *roles moved to Step 35*

---

## Step 10 — One-command setup (foundation)
**Goal**: `git clone` → one command → running stack. Makes every later phase reproducible.
**Depends on**: nothing (do first).

Tasks:
- [ ] `docker-compose.yml`: `db` (pgvector/pg16, named volume, port 5433) + `backend`
  (build from a new `backend/Dockerfile`, `depends_on: db`, `env_file: .env`, port 8001).
- [ ] `backend/Dockerfile`: python:3.11-slim, install `requirements.txt`, run
      `fetch_liveness_models` at build, `uvicorn backend.main:app`. Note: webcam access needs
      `--device /dev/video0` (document; compose `devices:` block, commented for no-cam CI).
- [ ] `Makefile`: `setup` (venv + pip + fetch-models + cp .env), `up`/`down` (compose),
      `dev` (uvicorn --reload), `enroll`, `calibrate`, `preview`, `fmt`, `lint`.
- [ ] `.dockerignore` (mirror `.gitignore` + `.venv`, `frontend/node_modules`).
- [ ] Add `GET /health` to `backend/main.py` (checks DB reachable) — compose healthcheck.

**New/changed**: `docker-compose.yml`, `backend/Dockerfile`, `Makefile`, `.dockerignore`,
`backend/main.py`, `.env.example`, `README.md`.
**Acceptance**: `make up` on a clean checkout brings up DB + backend; `curl :8001/health`
returns ok; `FACE_MATCH_ENABLED=false` path works with no webcam.

---

## Step 11 — Backend API expansion + live tap stream
**Goal**: REST + WebSocket surface the SPA will consume. No UI yet.
**Depends on**: Step 10.

Tasks:
- [ ] Read endpoints (extend `backend/main.py`, add `db.py` queries):
  - [ ] `GET /api/attendance?date=&status=&student_id=&limit=` — logs joined to student name.
  - [ ] `GET /api/students` — roster (no embeddings in payload).
  - [ ] `GET /api/stats/today` — counts by status (accepted/flagged/rejected/…).
  - [ ] `GET /api/config` — read-only view of active thresholds/flags (from `face`/`liveness`/`decision`).
- [ ] Live stream:
  - [ ] `backend/events.py` — tiny asyncio pub/sub (a set of subscriber queues; `publish(event)`).
  - [ ] `WS /ws/taps` — subscribe, stream tap events as JSON.
  - [ ] In `/tap`, after insert+notify, `events.publish({...})` for the tap. **Fail-open**:
        wrap in try/except so a broadcast error never affects the response.
- [ ] Auth: `OPERATOR_TOKEN` env + a `require_operator` dependency guarding `/api/*` writes
      (reads too, except `/health`). Add token to `.env.example`.

**New/changed**: `backend/events.py`, `backend/main.py`, `backend/db.py`, `.env.example`.
**Acceptance**: `curl` each endpoint returns expected JSON; `websocat ws://…/ws/taps` prints a
live event when a `/tap` fires (simulate with `curl -XPOST /tap`); a tap still logs if no WS
clients are connected.

---

## Step 12 — Frontend scaffold (SPA toolchain)
**Goal**: A buildable, empty-but-wired React app served by the backend.
**Depends on**: Step 11 (so it has an API to talk to).

Tasks:
- [ ] `frontend/` via Vite (`react-ts`). Add `node_modules/`, `frontend/dist/` to `.gitignore`.
- [ ] `vite.config.ts`: dev proxy `/api` + `/ws` → `http://localhost:8001`.
- [ ] App shell + router: routes `/` (dashboard) and `/kiosk`. Placeholder pages.
- [ ] Small API client (`src/api.ts`) + typed tap event; a `useTapStream()` WebSocket hook.
- [ ] Prod serving: `backend/main.py` mounts `StaticFiles(directory="frontend/dist")` at `/app`
      **only if the dir exists** (so backend still boots pre-build). SPA fallback to index.html.
- [ ] Makefile: `web-install`, `web-dev`, `web-build`. Compose: build step for the frontend
      (multi-stage Dockerfile or a `frontend` build container writing `dist`).

**New/changed**: `frontend/*`, `vite.config.ts`, `backend/main.py`, `Makefile`, `.gitignore`,
`.dockerignore`.
**Acceptance**: `make web-dev` serves the shell, hits `/api/health` through the proxy, and the
tap-stream hook logs live events; `make web-build` produces `dist/`, and the backend serves it
at `/app`.

---

## Step 13 — Operator dashboard (read views)
**Goal**: The demo-able screen — makes the whole system legible in a browser.
**Depends on**: Step 12.

Tasks:
- [ ] Login gate: token entry stored in `localStorage`, sent as auth header / WS query param.
- [ ] **Live feed**: newest taps stream in (name, time, status pill, face/liveness scores),
      rejected/flagged rows highlighted.
- [ ] **Today panel**: counts from `/api/stats/today` (present / flagged / rejected / unverified).
- [ ] **History table**: `/api/attendance` with date + status filters, pagination.
- [ ] Empty/error/loading states; responsive; readable on a projector.

**New/changed**: `frontend/src/pages/Dashboard.tsx` + components.
**Acceptance**: with the backend running, the dashboard shows today's counts, a filterable
history table, and a live tap appearing in the feed within ~1s of a `/tap` POST.

---

## Step 14 — Roster + browser enrollment (write views)
**Goal**: Manage students and enroll faces without the CLI.
**Depends on**: Step 13.

Tasks:
- [ ] Write endpoints (guard with `require_operator`):
  - [ ] `POST /api/students`, `PATCH /api/students/{id}`, `DELETE /api/students/{id}`
        (student_id, uid, name, guardian_email).
  - [ ] `POST /api/students/{id}/enroll` — accept N uploaded frames (multipart), reuse
        `face.encode_image` + averaging (mirror `backend/enroll.py`), store via
        `db.set_face_embedding`. Return per-frame usable/rejected feedback.
- [ ] Roster UI: table with add/edit/delete; validation; guardian email field.
- [ ] Browser enrollment: capture 3–5 shots from `getUserMedia` (operator laptop cam),
      preview, submit to enroll endpoint, show which frames had a usable face.
- [ ] Keep the "no image stored on disk" invariant — frames become an embedding, then dropped.

**New/changed**: `backend/main.py`, `backend/db.py` (maybe refactor `enroll.py` core into a
shared func), `frontend/src/pages/Roster.tsx`, enrollment component.
**Acceptance**: create a student in the UI, enroll from the browser webcam, then a `/tap` with
that UID produces a non-null `face_score`; deleting the student works; no image files written.

---

## Step 15 — Kiosk feedback screen
**Goal**: The tap-time experience for the kids. Highest deployment value.
**Depends on**: Step 11 (WS) + Step 12 (SPA). Independent of 13/14.

Tasks:
- [ ] `/kiosk` fullscreen route, unauthenticated, subscribes to `/ws/taps`.
- [ ] On event: big verdict — green ✓ + name on accepted, amber on flagged, red ✗ on
      rejected/spoof; "look at the camera / hold still" idle prompt between taps.
- [ ] Audio cues (accept chime / reject buzz); auto-reset to idle after a few seconds.
- [ ] Kiosk-hardening notes: fullscreen/kiosk browser, screensaver off, autostart URL
      `…/app/kiosk`. Document (don't automate) in README.

**New/changed**: `frontend/src/pages/Kiosk.tsx`, audio assets, `README.md`.
**Acceptance**: open `/app/kiosk`, POST a `/tap` for each status, and the screen shows the
correct verdict + name + sound within ~1s, then returns to idle. (Live webcam run is
**deferred** — needs the kiosk hardware; verify with simulated `/tap` POSTs.)

---

## Step 16 — Hardening & polish
**Goal**: Repo is clone-run-demo clean and safe to show.
**Depends on**: Steps 10–15 (do relevant bits as you go; finish here).

Tasks:
- [ ] `OPERATOR_TOKEN` required in non-dev; document generating one. Rate-limit login attempts.
- [ ] CORS locked to configured origin(s) via env.
- [ ] README screenshots/GIF of dashboard + kiosk; architecture diagram updated for the UI + WS.
- [ ] Optional CI: backend import/lint check + `web-build` on push.
- [ ] Update CLAUDE.md build order (Steps 10–16 done) and README "Status".

**Acceptance**: fresh clone → `make setup && make up && make web-build` → dashboard + kiosk both
reachable, auth enforced, README shows real screenshots.

---

## Cross-cutting definition of done (every phase)
- Fail-open preserved: `/tap` never breaks because a new surface is down.
- New config in `.env.example`; nothing secret committed.
- README "Status" + CLAUDE.md build order kept in sync.
- Non-hardware paths verified with simulated `/tap` POSTs; anything needing the **webcam or
  kiosk hardware is explicitly deferred and noted**, per the existing Step 7–9 convention.

## Carried-over deferred items (from Steps 7–9, still open)
- Liveness threshold calibration with real spoof samples (`calibrate --metric liveness`).
- Real guardian SMTP send against a live provider.
- Turning on `ENFORCE_2FA=true` after live validation.

---

# Backbone track (Steps 20–23)

Parallel to the UI track (10–16). These are domain/quality steps a serious reviewer expects of a
**children's biometric attendance system** — responsibility, meaning, reliability, anti-fraud.
Independent of the UI phases except where noted; can be scheduled around them.

## Progress summary (backbone)
- [ ] Step 20 — Privacy & compliance
- [ ] Step 21 — Attendance sessions + guardian digest
- [ ] Step 22 — Reliability & operability
- [ ] Step 23 — Anti-fraud extensions

---

## Step 20 — Privacy & compliance
**Goal**: Handle minors' biometric data responsibly; make it a documented feature.
**Depends on**: soft — audit log pairs with `OPERATOR_TOKEN` (Step 11); consent gate hooks into
enrollment (Step 14). Schema + purge job can land anytime.

Tasks:
- [ ] **Consent gating**: `students.face_consent BOOLEAN` (+ consent timestamp). Enrollment and
      face matching refuse / skip when consent is false; tap still logs NFC-only. `.env` default policy.
- [ ] **Retention/purge**: env `ATTENDANCE_RETENTION_DAYS`, `SCORE_RETENTION_DAYS`; a purge task
      (cron or `make purge`) that deletes old logs / nulls old raw scores. Never touches roster.
- [ ] **Right-to-erasure**: `DELETE /api/students/{id}` also drops the embedding + logs (or
      anonymizes), writing an erasure audit entry.
- [ ] **Operator audit log**: `audit_log` table (actor, action, target, ts); write on every
      enroll/delete/roster edit. Read endpoint for the dashboard.
- [ ] **Embedding encryption at rest** (optional/2nd pass): pgcrypto or app-level; document the
      key-management tradeoff. Note: embeddings are non-invertible to images but are still PII.
- [ ] **Privacy doc**: `docs/privacy.md` — what's stored (embedding, not images), why, retention,
      erasure, consent. Link from README.

**New/changed**: `backend/schema.sql`, `backend/db.py`, `backend/main.py`, `backend/enroll.py`,
`docs/privacy.md`, `.env.example`, `README.md`.
**Acceptance**: enrolling without consent is refused; purge removes rows older than the window and
keeps the roster; deleting a student erases embedding + logs and records an audit entry.

---

## Step 21 — Attendance sessions + guardian digest
**Goal**: Turn isolated tap rows into attendance *meaning* (present, check-in/out, absences).
**Depends on**: Step 8 (SMTP, done) for the digest. Reporting endpoints pair well with Step 13.

Tasks:
- [ ] **Sessions**: derive check-in vs check-out by pairing a student's taps within a day
      (first tap = in, next = out; configurable). Add a view/query for "present now" + duration.
      Decide: store a `direction`/session table, or compute on read. Prefer a `sessions` view first.
- [ ] **Present-today / absence**: `GET /api/attendance/summary?date=` — expected (roster or a
      group) vs. who tapped → present / absent / late lists.
- [ ] **Late flag**: env/schedule cutoff time; mark taps after it.
- [ ] **Guardian digest**: batched daily/weekly summary email (opt-in per student), replacing or
      complementing the per-tap notify. Reuse `backend/notify.py` SMTP path; add a `make digest`
      / scheduled task.
- [ ] **Export**: `GET /api/attendance.csv` with filters.

**New/changed**: `backend/db.py`, `backend/main.py`, a `backend/digest.py`, `schema.sql` (if a
sessions table), `.env.example`.
**Acceptance**: two taps by one student in a day resolve to an in/out session with a duration; the
summary lists absent students for a date; a digest email renders the day's attendance via the SMTP
stub (real send deferred).

---

## Step 22 — Reliability & operability
**Goal**: Trustworthy 24/7 kiosk; fast diagnosis when something breaks.
**Depends on**: none (extends existing systemd + failed-tap queue).

Tasks:
- [ ] **`make doctor`** (`backend/doctor.py`): one-shot check of camera, DB, models present,
      serial port, SMTP config → per-item pass/fail + hints. No live tap needed.
- [ ] **Tamper/health alerts**: on camera-open failure, serial disconnect, or DB-unreachable,
      notify the operator (reuse notify path / a webhook). Debounced.
- [ ] **Metrics**: `GET /metrics` (Prometheus text) — tap counts by status, tap latency, camera
      fps, error counters.
- [ ] **Local roster cache**: cache uid→student so taps still identify + verify during a brief
      Postgres outage; reconcile on reconnect (extends `failed_taps.jsonl`).
- [ ] **DB backup**: `make backup` = `pg_dump` wrapper to a timestamped file; document restore.

**New/changed**: `backend/doctor.py`, `backend/main.py` (metrics), `backend/serial_reader.py`
(alerts/cache), `Makefile`, `README.md`.
**Acceptance**: `make doctor` reports each subsystem; killing the DB triggers an alert and taps
still identify from cache; `/metrics` scrapes; `make backup` writes a restorable dump.

---

## Step 23 — Anti-fraud extensions
**Goal**: Harden the 2FA mission beyond the single-frame checks.
**Depends on**: Steps 6–7 (done). Cooldown is independent; tailgating reuses the capture.

Tasks:
- [ ] **Tap cooldown**: reject/dedupe a repeat of the same UID within env `TAP_COOLDOWN_SEC`
      (kills accidental double-logs + rapid clone probing). Log as a distinct status.
- [ ] **Tailgating warning**: >1 usable face in the tap frame → flag on the log + notify.
- [ ] **Repeated-unknown-card alert**: N unregistered taps in a window → operator alert (probe
      detection).
- [ ] **Active-liveness escalation**: only when passive liveness *flags*, prompt a blink/turn
      (active check) rather than slowing every tap. Design as an optional second capture.

**New/changed**: `backend/decision.py`, `backend/main.py`, `backend/face.py` (multi-face count),
`backend/liveness.py` (active mode), `.env.example`.
**Acceptance**: a second tap of the same card within the window is deduped; a two-face frame flags
tailgating; repeated unknown cards fire one debounced alert. (Active-liveness live test deferred to
hardware.)

---

# Flow track (Steps 30–35) — continuous multi-student guardpost

The core-model evolution: a guardpost handling **3–5 students/second**. Bursts of card taps, a
**continuous camera** watching many faces moving in/out of frame, faces correlated to taps, a
public boxes-only "mirror" viewer beside the gate, an in-app registration wizard, and a manual
review queue. Shifts the system from **per-tap 1:1 verification** to a **continuous perception
pipeline + async tap↔face correlation**. **Designed for the RTX 1050 GPU box** — the current
CPU box is a ~1/s functional demo only.

## Locked decisions (from design review)
- **Strict card-required**: no tap = not present. Face only *verifies* the tapped student.
- **Cardless 1:N = tailgater-ID tool, not a presence path**: a tracked face matching no buffered
  tap is searched against the full gallery only to *name* the intruder for review — never present.
- **GPU-first** (`USE_GPU=true`, RTX 1050); CPU stays a dev demo.
- **Register Student**: in-app, admin-only full-screen wizard (no separate app).
- **Public viewer**: boxes + status only, **no names / PII**.

## Prerequisites (from other tracks — do first)
- **UI Step 11** (events bus + async infra) and **UI Step 12** (SPA scaffold) underpin this track.
- This track **supersedes/absorbs**: UI Step 15 (kiosk) → the boxes-only **viewer** (Step 35);
  UI Step 14 (browser enroll) → the **register wizard** (Step 35); UI Step 16 roles → **roles**
  (Step 35); Backbone Step 23 tailgating/cooldown → realized inside the **matcher** (Step 31).
  Build those concepts here, not twice.

## Progress summary (flow)
- [ ] Step 30 — Perception service (single camera owner)
- [ ] Step 31 — Tap buffer + tap↔face correlation (matcher)
- [ ] Step 32 — Throughput / perf hardening (GPU)
- [ ] Step 33 — Identity & matching features
- [ ] Step 34 — Manual review queue
- [ ] Step 35 — Multi-view UI + register-student

## Conflicts this track resolves (current code that must change)
- `face.capture_probe()` / `preview.py` each open the webcam per call and hold it exclusively →
  replaced by **one camera-owner process**; everything else subscribes.
- `/tap` returns the match inline → becomes an **async ack**; correlation resolves later.
  `serial_reader.py` must tolerate an ack-only response.
- `FACE_THRESHOLD=0.5` (1:1) is unsafe for whole-DB 1:N → higher threshold **+ top1−top2 margin**.
- **Bug fixed in passing** (Step 33): `enroll.py` `_from_capture` treats `face.capture_probe()` as
  an embedding, but it returns a `Probe(frame,bbox,embedding)` tuple → `--capture` enroll is broken.

---

## Step 30 — Perception service (single camera owner)
**Goal**: One long-running process owns the camera and runs detect → track → recognize
continuously, so cost is per-*track* not per-*frame*. Foundation for the whole track.
**Depends on**: UI Step 11 (events bus); GPU design.

Tasks:
- [ ] `backend/perception.py`: camera-owner loop; publishes (a) annotated frames (viewer) and
      (b) recognized-face events `{track_id, bbox, embedding, live_score, ts}` (matcher).
- [ ] **Face tracking** (IoU/centroid or ByteTrack-lite): stable track IDs across frames; run
      recognition **once per new track**, not per frame (throughput + "in/out of frame").
- [ ] Refactor `backend/face.py`: split camera ownership out of `capture_probe`; keep `detect`,
      `embed`, `cosine`, `gpu_runtime`, `largest_usable` as reusable primitives.
- [ ] **Fail-open**: if perception is down, `/tap` falls back to card-only *flagged/unverified* logging.

**New/changed**: `backend/perception.py`, `backend/face.py`, `backend/events.py`, `.env.example`.
**Acceptance**: run against a **video file / image sequence** (not the live cam) — track IDs stay
stable, recognition fires once per track, annotated frames + face events publish on the bus.

---

## Step 31 — Tap buffer + tap↔face correlation (matcher)
**Goal**: Correlate a burst of taps with observed faces under strict card-required rules.
**Depends on**: Step 30.

Tasks:
- [ ] `/tap` → **async enqueue + ack**. Buffer `{uid, student_id, embedding, ts}` for
      `ASSOC_WINDOW_SEC` (default 4 s).
- [ ] `backend/matcher.py`: **Hungarian assignment** of buffered-tap embeddings ↔ recognized-face
      embeddings (cosine), within the window. Rules:
  - tap + matching face ≥ threshold → **present (verified)**.
  - tap + no face in window → **flagged: no-face** → review.
  - tap + face below threshold → **flagged: mismatch** → review.
  - face matching no tap → **tailgating**: cardless whole-DB search to name it → alert + review.
  - liveness fail on a matched face → **flagged: spoof**.
- [ ] Extend `backend/decision.py` statuses (`tailgating`, `no_face`, …); write logs via `db.py`.

**New/changed**: `backend/matcher.py`, `backend/main.py`, `backend/decision.py`, `backend/db.py`,
`backend/serial_reader.py`, `.env.example`.
**Acceptance**: feed synthetic tap bursts + synthetic face-event streams (recorded embeddings) →
correct outcomes across edge cases (more taps than faces, more faces than taps, below-threshold,
no-face timeout, tailgater).

---

## Step 32 — Throughput / perf hardening (GPU)
**Goal**: 3–5 students/s on the RTX 1050.
**Depends on**: Steps 30–31 + **GPU hardware (live perf deferred)**.

Tasks:
- [ ] `onnxruntime-gpu` path; once-per-track recognition; frame-skip + `FACE_DET_SIZE` tuning;
      optional batched recognition; profile to target.

**Acceptance (deferred — hardware)**: sustained 3–5 students/s with acceptable accuracy on the 1050.

---

## Step 33 — Identity & matching features
**Goal**: cardless 1:N (tailgater ID + manual lookup), dup-enrollment detection, re-enroll reminders.
**Depends on**: schema + Step 30.

Tasks:
- [ ] Schema: `students.embed_model TEXT`, `students.enrolled_at TIMESTAMPTZ`; **pgvector ANN index**.
- [ ] **Cardless 1:N** search API (matcher tailgater ID; also manual lookup).
- [ ] **Duplicate-enrollment detection**: on enroll, 1:N vs gallery → warn if the face already exists.
- [ ] **Re-enrollment reminders**: flag embeddings older than `REENROLL_AFTER_DAYS` or an older
      `embed_model`.
- [ ] **Fix `enroll.py --capture`** (use `probe.embedding`); extract a shared enroll core reused by
      the wizard (Step 35).

**New/changed**: `backend/schema.sql`, `backend/db.py`, `backend/enroll.py`, `backend/main.py`,
`.env.example`.
**Acceptance**: dup-check warns on a re-enroll of an existing face; re-enroll report lists stale
embeddings; `--capture` enroll works again — all against a seeded gallery, no live cam.

---

## Step 34 — Manual review queue
**Goal**: Flagged students get pulled and resolved by staff; resolutions feed calibration.
**Depends on**: Step 31 + dashboard (UI Step 13).

Tasks:
- [ ] Flagged taps (no-face / mismatch / spoof / tailgating / low-confidence / dup) → review queue
      (`review_queue` table or status filter).
- [ ] Operator **confirm / override / request re-tap**; resolution logged (ties to Step 20 audit).
- [ ] Endpoints + dashboard view.

**New/changed**: `backend/schema.sql`, `backend/db.py`, `backend/main.py`, dashboard components.
**Acceptance**: a simulated flagged tap appears in the queue; confirm/override updates the log and
writes an audit entry.

---

## Step 35 — Multi-view UI + register-student (reconciles UI Steps 13–16)
**Goal**: Admin + public-viewer windows running simultaneously, plus in-app enrollment.
**Depends on**: UI Step 12 (SPA), Steps 30–34.

Tasks:
- [ ] **Roles**: promote single `OPERATOR_TOKEN` → an `operators` table with `admin` / `viewer` roles.
- [ ] **Admin view**: full dashboard (live feed, review queue, roster, stats).
- [ ] **Viewer view** (public, beside the gate): subscribes to the annotated-frame stream; **boxes +
      status only, no names** (green ✓ / amber hold-still / red see-the-guard). **MJPEG** stream v1.
- [ ] **Register Student**: admin-only full-screen wizard — details → webcam capture 3–5 shots →
      **dup-check (Step 33)** → save; reuses the fixed enroll core. Keep "no image stored on disk".
- [ ] Both views run simultaneously (separate windows/routes).

**New/changed**: `backend/main.py` (roles, MJPEG stream), `frontend/src/pages/{Viewer,Register}.tsx`,
auth components.
**Acceptance**: viewer renders boxes from a simulated frame/event stream with no names; register
wizard enrolls from the browser webcam (dup-check runs); admin and viewer usable at once.

---

## Flow-track deferred items (need GPU box / live cam / kiosk)
- Real 3–5 students/s throughput profiling on the RTX 1050 (`onnxruntime-gpu`).
- Live multi-face guardpost accuracy + 1:N threshold / top1−top2 margin calibration.
- (Carried) liveness threshold calibration, real SMTP send, `ENFORCE_2FA=true`.

## Open defaults (proceeding unless changed)
- `ASSOC_WINDOW_SEC=4`; 1:N threshold ~0.6 with top1−top2 margin ~0.1; MJPEG viewer v1; roles via a
  small `operators` table (not external SSO).
