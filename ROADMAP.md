# nfc-scan — build roadmap (Steps 10–54, five tracks)

Handoff / build list. **Do the phases in order within a track** — each depends on the ones above
it. Steps 1–9 (NFC → log → face → liveness → notify → 2FA) are done; see README "Status" and
CLAUDE.md "Build order". This doc picks up at Step 10.

Tracks: **UI (10–16)** · **Backbone (20–23)** · **Flow (30–35)** · **Deploy (40–44)** ·
**Tuning (50–54)**. Cross-cutting constraints/failure modes live in `docs/design-notes.md`.

The tracks are grouped by theme; the **Build sequence** below is the actual order to build in
(it interleaves the tracks by dependency + value). Follow the sequence, not the track numbers.

> **Active handoff:** a set of **UI-only** surfaces over already-built endpoints (public Viewer,
> attendance summary/sessions/CSV, audit/re-enroll/face-lookup panels, ops readout, kiosk audio)
> is specced in **[`handoff.md`](handoff.md)** — pure frontend, **no backend changes**. Pick tasks
> from there before opening new backend work.

> **What's already built:** see **[`docs/build-log.md`](docs/build-log.md)** for the detailed
> per-step record (files, env knobs, verification). Read the relevant entry before modifying a
> built area. This ROADMAP is the *plan*; the build-log is the *state*.

---

## Build sequence (cross-track priority order)

Dependency-respecting, value-early. **▶ = start here.** `[CPU]` buildable + simulation-testable
now; `[GPU/HW]` logic buildable now but final verification needs the RTX 1050 / live devices.

**Phase A — Foundation** *(unblocks everything; do strictly in order)*
1. ▶ **Step 10** — one-command setup `[CPU]` — also seeds the installer skeleton (Deploy) + gives Tuning a DB.
2. **Step 11** — API + events bus + async `/tap` + `OPERATOR_TOKEN` `[CPU]` — prereq for perception, dashboard, everything.
3. **Step 12** — SPA scaffold `[CPU]` — prereq for every UI surface.
4. *(optional here)* **Step 44** — release CI early, to protect the build as it grows.

**Phase B — Perception core** *(the keystone architecture change)*
5. **Schema pass** — land the additive columns together (idempotent ALTERs): `status` (done), `embed_model`, `enrolled_at` (Step 33), `face_consent` (Step 20), `review_queue` (Step 34).
6. **Step 30** — perception service (single camera owner, tracking, publish streams) `[GPU/HW]`.
7. **Step 31** — matcher (async correlation, Hungarian, strict rules; also realizes Backbone 23 cooldown/tailgating) `[CPU]` sim-testable.
8. **Step 33 (part)** — fix `enroll --capture` + extract shared enroll core `[CPU]` — quick; unblocks the register wizard.

**Phase C — Data model & responsibility** *(can overlap late B)*
9. **Step 20** — privacy/consent/audit `[CPU]` — **consent gate must exist before enrolling real children** (legal).
10. **Step 33 (rest)** — cardless 1:N (tailgater ID), dup-enroll detection, re-enroll reminders `[CPU]`.
11. **Step 21** — attendance sessions + guardian digest `[CPU]`.

**Phase D — Runtime tuning** *(needs perception + a settings store)*
12. **Step 50** — runtime settings layer `[CPU]` ✓ (write-gate on `OPERATOR_TOKEN` until roles land in 35).
13. **Step 51** — model hot-reload `[GPU/HW]`.
14. **Step 52** — device + resolution controls `[GPU/HW]`.
15. **Step 22 (part)** — `make doctor` + `GET /metrics` `[CPU]` ✓ (backup + local cache still open).
16. **Step 53** — optimizer (button + presets + adaptive) `[GPU/HW]`.

**Phase E — UI surfaces** *(needs SPA + the backend features above)*
17. **Step 13** — operator dashboard (read views) `[CPU]` ✓.
18. **Step 34 (backend)** — review queue API endpoints `[CPU]` ✓ (backend done; frontend panel still open).
19. **Step 35 (backend)** — student CRUD + enroll API `[CPU]` ✓ (backend done; frontend wizard still open).
20. **Step 54** — settings/optimizer UI panel `[CPU]`.
21. **Step 23 (rest)** — anti-fraud extras not already in the matcher `[CPU]`.

**Phase F — Ship** *(needs the full app)*
22. **Step 40** — appliance provisioning `[GPU/HW]`.
23. **Step 41** — downloadable "button" `[GPU/HW]`.
24. **Step 42** — in-UI first-run wizard `[CPU]` (needs doctor 22 + register 35).
25. **Step 43** — updates / backup / recovery `[CPU]`.
26. **Step 44** — release CI (if not done in Phase A).
27. **Step 16** — final hardening, CORS lockdown, README screenshots `[CPU]`.

**Superseded — do NOT build as written**: UI **Step 14** (browser enroll) → folded into the register
wizard (Step 35); UI **Step 15** (kiosk) → the boxes-only viewer (Step 35). Their concepts live in 35.

**The wall**: everything through Phase E is buildable + simulation-verifiable on the current CPU box.
`[GPU/HW]` items build their *logic* now; their *acceptance* (real throughput, hot-swap timing,
device install) waits for the RTX 1050. Phase F is mostly on-box.

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
- [x] Step 10 — One-command setup (foundation) — `docker-compose.yml`, `backend/Dockerfile`, `Makefile`, `.dockerignore`, `GET /health`. ⚠ built on CPU box; `make up` not yet run end-to-end on a clean checkout.
- [x] Step 11 — Backend API expansion + live tap stream — `GET /api/{attendance,students,stats/today,config}`, `WS /ws/taps`, `backend/events.py` pub/sub, `OPERATOR_TOKEN` auth. Verified live (REST + WS event on `/tap`). *(prereq for Flow track)*
- [x] Step 12 — Frontend scaffold (SPA toolchain) — Vite+React+TS `frontend/`, dev proxy (`/api`+`/ws`+`/health`→:8001), router (`/`, `/kiosk`), `src/api.ts` + `useTapStream()` hook, backend serves `dist` at `/app` (SPA fallback), multi-stage Dockerfile. Verified: `web-build`→backend `/app`, dev proxy live. *(prereq for Flow track)*
- [x] Step 13 — Operator dashboard (read views) — auth gate, today panel (counts + status pills), live feed (WS, highlights), history table (date/status filters, pagination), responsive layout. Pure frontend (`frontend/src/components/{TodayPanel,LiveFeed,HistoryTable}.tsx`, `Dashboard.tsx` rewrite, `api.ts` typed `Config`/`AuditEntry`/`ReviewItem`, `index.css` utilities). No backend changes.
- [x] Step 14 — Roster + browser enrollment — table with add/edit/delete/consent (`Roster.tsx`), webcam capture → enroll (`Register.tsx`). Pure frontend consuming existing backend endpoints.
- [x] Step 15 — Kiosk verdict screen — fullscreen color-coded tap feedback with auto-reset (`Kiosk.tsx` rewrite). Audio cues via Web Audio API (accept chime + reject buzz), mute toggle, armed after first gesture.
- [x] Handoff tasks 1–9 — 7 new pages (`Viewer`, `Summary`, `Sessions`, `Audit`, `Reenroll`, `Lookup`, `Ops`) + CSV export + Kiosk audio. Pure frontend, zero backend edits. `api.ts` gained `reqBlob`/`reqText` helpers + 6 endpoint wrappers. Task 10 (polish/README) deferred.
- [ ] Step 16 — Hardening & polish — OPERATOR_TOKEN required in non-dev, CORS, README screenshots, CI. CLAUDE.md and ROADMAP.md sync.

---

# UI track (Steps 10–16) — one-command setup, API, SPA, dashboard

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
- [x] Login gate: token entry stored in `localStorage`, sent as auth header / WS query param.
- [x] **Live feed**: newest taps stream in (name, time, status pill, face/liveness scores),
      rejected/flagged rows highlighted.
- [x] **Today panel**: counts from `/api/stats/today` (present / flagged / rejected / unverified).
- [x] **History table**: `/api/attendance` with date + status filters, pagination.
- [x] Empty/error/loading states; responsive; readable on a projector.

**New/changed**: `frontend/src/components/{TodayPanel,LiveFeed,HistoryTable}.tsx` (new),
`frontend/src/pages/Dashboard.tsx` (rewrite), `frontend/src/api.ts` (typed Config, extended
Student, AuditEntry, ReviewItem placeholders), `frontend/src/App.tsx` (nav removed, auth
lives in Dashboard), `frontend/src/index.css` (status colors, responsive, dash-grid).
**No backend changes.**
**Acceptance**: with the backend running, the dashboard shows today's counts, a filterable
history table, and a live tap appearing in the feed within ~1s of a `/tap` POST.

---

## Step 14 — Roster + browser enrollment (write views)
**Goal**: Manage students and enroll faces without the CLI.
**Depends on**: Steps 13 (auth).

Tasks:
- [x] Write endpoints (guard with `require_operator`):
  - [x] `POST /api/students`, `PATCH /api/students/{id}`, `DELETE /api/students/{id}`
        (student_id, uid, name, guardian_email).
  - [x] `POST /api/students/{id}/enroll` — accept N uploaded frames (multipart), reuse
        `face.encode_image` + averaging (mirror `backend/enroll.py`), store via
        `db.set_face_embedding`. Return per-frame usable/rejected feedback.
- [x] Roster UI: table with add/edit/delete; validation; guardian email field.
- [x] Browser enrollment: capture 3–5 shots from `getUserMedia` (operator laptop cam),
      preview, submit to enroll endpoint, show which frames had a usable face.
- [x] Keep the "no image stored on disk" invariant — frames become an embedding, then dropped.
- [x] Settings UI: editable runtime settings page (`Settings.tsx`) consuming `GET/PUT /api/settings`.

**New/changed**: `backend/main.py`, `backend/db.py` (refactored `enroll.py` core into shared
funcs), `frontend/src/pages/Roster.tsx`, `frontend/src/pages/Register.tsx`,
`frontend/src/pages/Settings.tsx`.
**Acceptance**: create a student in the UI, enroll from the browser webcam, then a `/tap` with
that UID produces a non-null `face_score`; deleting the student works; no image files written.

---

## Step 15 — Kiosk feedback screen
**Goal**: The tap-time experience for the kids. Highest deployment value.
**Depends on**: Step 11 (WS) + Step 12 (SPA). Independent of 13/14.

Tasks:
- [x] `/kiosk` fullscreen route, unauthenticated, subscribes to `/ws/taps`.
- [x] On event: big verdict — green ✓ + name on accepted, amber on flagged, red ✗ on
      rejected/spoof; idle prompt ("Tap your card") with connection indicator.
- [x] Audio cues (accept chime / reject buzz); auto-reset to idle after 5s (done).
- [ ] Kiosk-hardening notes: fullscreen/kiosk browser, screensaver off, autostart URL
      `…/app/kiosk`. Document (don't automate) in README.

**New/changed**: `frontend/src/pages/Kiosk.tsx`, audio assets, `README.md`.
**Acceptance**: open `/app/kiosk`, POST a `/tap` for each status, and the screen shows the
correct verdict + name within ~1s, then returns to idle after 5s. (Live webcam run is
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
- [x] Step 20 — Privacy & compliance — consent gate (`FACE_CONSENT_REQUIRED` + `students.face_consent`), retention/purge (`make purge`, `ATTENDANCE_/SCORE_RETENTION_DAYS`), right-to-erasure (`DELETE /api/students/{id}`), `audit_log` (+ `GET /api/audit`), `docs/privacy.md`. Also landed the **Phase B schema pass** (`embed_model`, `enrolled_at`, `face_consent`, `audit_log`, `review_queue`). Encryption-at-rest deferred (documented 2nd pass).
- [x] Step 22 (part) — `make doctor` (`backend/doctor.py`), `GET /metrics` (Prometheus)
- [x] Step 21 — Attendance sessions + guardian digest — `backend/schema.sql` (attendance_sessions view), `db.py` (LATE_CUTOFF, get_sessions, get_summary, get_attendance_csv, _is_late), `main.py` (`GET /api/attendance/summary`, `GET /api/attendance/sessions`, `GET /api/attendance.csv`), `backend/digest.py` (one-shot CLI guardian batch email), `Makefile` (digest target), `.env.example` (LATE_CUTOFF). Verified live: sessions paired, summary present/absent/late correct, CSV exports, digest dry-run prints formatted sessions with durations.
- [x] Step 22 (part) — `make doctor` (`backend/doctor.py`: checks DB, face model, liveness, camera, serial, SMTP), `GET /metrics` (Prometheus: tap counts by status, last-minute rate, camera FPS)
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

> **Read [`docs/design-notes.md`](docs/design-notes.md) first.** It records the cross-cutting
> constraints and failure behaviors this track must honor — single camera owner, **single backend
> worker**, reader-throughput ceiling, camera-dead degraded mode, tap↔face correlation edge cases,
> and the legal/consent + accuracy-eval gates before real deployment.

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
- [x] Step 30 — Perception service (single camera owner) — `backend/perception.py`: camera-owner loop, greedy-IoU `FaceTracker` (stable IDs, recognition once per new track), in-process `on_frame`(boxes)/`on_face`(embedding, PII) sinks; `face.open_capture()` extracted; `/tap` card-only `unverified` when perception owns the cam. Default OFF. Verified with a synthetic image sequence (deterministic). ⚠ live-cam / video-file + GPU acceptance deferred (`[GPU/HW]`).
- [x] Step 31 — Tap buffer + tap↔face correlation (matcher) — `backend/matcher.py`: async `/tap` enqueue+ack, `ASSOC_WINDOW_SEC` buffer, Hungarian (scipy) tap↔face assignment, strict rules → statuses `accepted`/`mismatch`/`no_face`/`spoof`/`tailgating`; cardless 1:N tailgater ID via `db.search_face` (pgvector); `TAP_COOLDOWN_SEC` debounce; bounded face buffer. Wired into `main.py` startup (perception→matcher, resolve loop, camera thread). Verified: 10 edge-case unit tests (incl. Hungarian cross-order) + live queued→async-resolve end-to-end. ⚠ live-cam correlation deferred (`[GPU/HW]`).
- [ ] Step 32 — Throughput / perf hardening (GPU)
- [x] Step 33 — Identity & matching features — cardless 1:N (`db.search_face` + `POST /api/search-face`), dup-enroll detection (`db.find_duplicate`), re-enroll reminders (`GET /api/reenroll-due`), HNSW ANN index, `--capture` fix + shared enroll core.
- [x] Step 34 — Manual review queue — `GET /api/review` + `POST /api/review/{id}/resolve` (backend in management layer), Review.tsx frontend (table with confirm/override/dismiss per row). Verified live.
- [ ] Step 35 — Multi-view UI + register-student — register wizard done (`Register.tsx`, webcam capture → enroll), viewer view done (`Viewer.tsx`, boxes-only MJPEG). Remaining: roles (operators table).

## Conflicts this track resolves (current code that must change)
- `face.capture_probe()` / `preview.py` each open the webcam per call and hold it exclusively →
  replaced by **one camera-owner process**; everything else subscribes.
- ✅ **Resolved (Step 31)**: when `PERCEPTION_ENABLED`, `/tap` returns an **async ack**
  (`{"status":"queued"}`) and correlation resolves later; `serial_reader.py` tolerates the ack-only
  response (2xx). The 1:1 inline path stays as the fallback when perception is off.
- `FACE_THRESHOLD=0.5` (1:1) is unsafe for whole-DB 1:N → higher threshold **+ top1−top2 margin**
  (still open — Step 33 rest; the matcher currently names a tailgater at `TAILGATE_NAME_THRESHOLD`).
- ✅ **Fixed (Step 33)**: `enroll.py` `_from_capture` now uses `probe.embedding` (was treating the
  `Probe(frame,bbox,embedding)` tuple as an embedding) → `--capture` enroll works.

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
- [x] Schema: `students.embed_model TEXT`, `students.enrolled_at TIMESTAMPTZ` (Step 20 pass); **pgvector HNSW ANN index** (`students_face_embedding_hnsw`).
- [x] **Cardless 1:N** search API — `db.search_face` (matcher tailgater ID) + `POST /api/search-face` (image upload → nearest students, manual lookup).
- [x] **Duplicate-enrollment detection**: `db.find_duplicate` on enroll (1:N vs gallery, `DUP_ENROLL_THRESHOLD`) → warns (doesn't block); logged in audit.
- [x] **Re-enrollment reminders**: `db.stale_enrollments` + `GET /api/reenroll-due` — flags references older than `REENROLL_AFTER_DAYS` or a non-current `embed_model`.
- [x] **Fix `enroll.py --capture`** (use `probe.embedding`); extract a shared enroll core reused by
      the wizard (Step 35). — done (Phase B item 8): `embeddings_from_frames` / `average_reference` /
      `enroll_student` extracted, CLI delegates to them.

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

---

# Deploy track (Steps 40–44) — distribution & one-touch install

**The repo's real job**: get this onto the RTX 1050 guardpost box **easily** and have it **run as an
appliance** (auto-start on boot into the UI) with **non-technical** hands doing the least possible.

## Locked decisions
- **Primary target: Linux appliance.** Most reliable for GPU + webcam + serial + kiosk auto-start;
  reuses the existing systemd units. **Windows Inno Setup `.exe`** is a documented *alternative* if
  the box must run Windows (accepts more fragility + a manual NVIDIA-driver step).
- **Appliance model**: a technician provisions the box **once** (one installer or a pre-flashed
  image); **staff just power it on** and it boots into the running guardpost. A literal single-exe
  for end-users is *not* the goal — the appliance is.
- **No terminal for staff**: first-run + daily operation happen entirely in the browser UI.

## Reconciliation
- **UI Step 10 (one-command setup) seeds this track** — its docker-compose/Makefile/`fetch-models`
  are the dev-time ancestor of the appliance installer. Grow the installer *from* Step 10; keep the
  systemd units (backend, reader, + new perception) as the shared runtime.
- Culminates **after the Flow track** (needs the full app), but scaffold the installer skeleton, CI,
  and kiosk config early so every feature is installed the same way it'll ship.

## Progress summary (deploy)
- [ ] Step 40 — Appliance provisioning (one script, per box)
- [ ] Step 41 — Wrap as a downloadable "button" (GitHub Release artifact)
- [ ] Step 42 — In-UI first-run wizard (no terminal)
- [ ] Step 43 — Updates, backup & recovery
- [ ] Step 44 — Release engineering (CI → installer artifacts)

---

## Step 40 — Appliance provisioning (one script, per box)
**Goal**: fresh box → one command → reboot → boots into the running guardpost.
**Depends on**: a runnable app (grows with the build); reuses systemd units.

Tasks (Linux primary):
- [ ] `deploy/install.sh`: verify/install **NVIDIA driver + CUDA/cuDNN** (or check + link docs);
      install **Postgres + pgvector** (native), create DB + schema; create the Python env +
      `onnxruntime-gpu` + deps; **fetch models**; build + install the SPA.
- [ ] Install + enable systemd units (backend, perception, reader); `loginctl enable-linger`;
      configure **kiosk auto-start** (auto-login + `chromium --kiosk` to the viewer/admin URL).
- [ ] Write `.env` with sane defaults + `USE_GPU=true`; prompt only for essentials.
- [ ] `deploy/preflight` check: GPU present? camera at `/dev/video0`? serial at `/dev/ttyACM0`?

**New/changed**: `deploy/install.sh`, `deploy/preflight`, `deploy/systemd/*.service`,
`deploy/kiosk/*`, `README.md`.
**Acceptance**: on a clean Linux box, run the installer → reboot → the guardpost UI is on screen and
a simulated `/tap` logs. (Live GPU/cam verification deferred to the actual box.)

## Step 41 — Wrap as a downloadable "button"
**Goal**: one file from GitHub Releases, double-click / run, guided to done.
**Depends on**: Step 40.
Tasks:
- [ ] Linux: self-extracting `.run` (or `.deb` / AppImage-style launcher) wrapping `install.sh` with
      a friendly TUI/GUI + the preflight checks.
- [ ] **Windows alternative** (only if box is Windows): Inno Setup `.exe` — embedded-Python backend +
      bundled SPA + portable Postgres + model download + Task Scheduler auto-start + documented driver step.
**Acceptance**: download a single Release asset, run it, reach a working install without editing files.

## Step 42 — In-UI first-run wizard (no terminal)
**Goal**: non-technical setup entirely in the browser.
**Depends on**: Step 35 (UI), Step 40.
Tasks:
- [ ] First-run flow: set admin password/token → **test camera / reader / GPU** (health panel, reuses
      `doctor`, Backbone Step 22) → enroll first student (register wizard, Step 35).
**Acceptance**: a non-technical user completes setup in the browser with no shell.

## Step 43 — Updates, backup & recovery
**Goal**: keep an appliance current and safe without a technician on-site.
**Depends on**: Step 40.
Tasks:
- [ ] One-click / scheduled **update** (pull release → migrate schema → restart), preserving data.
- [ ] **Backup/restore** (reuse Backbone Step 22 `pg_dump`); **factory-reset / re-provision**.
**Acceptance**: updating to a new release preserves roster + attendance; restore recovers a backup.

## Step 44 — Release engineering (CI)
**Goal**: tagging a release auto-produces the installer artifacts.
**Depends on**: Steps 40–41.
Tasks:
- [ ] GitHub Actions: build SPA, bundle backend, run tests, produce installer artifact(s), attach to
      a **GitHub Release**; semantic versioning; changelog.
**Acceptance**: pushing a tag yields downloadable installer artifacts on the Releases page.

## Deploy-track deferred (needs the actual box)
- Live install on the RTX 1050 (driver/CUDA/onnxruntime-gpu), kiosk auto-start, camera + serial on
  the real hardware. The installer is built + testable in a VM/container up to the GPU/device steps.

---

# Tuning track (Steps 50–54) — runtime device/resolution/optimizer panel

**Goal**: one build **adapts to whatever machine it's installed on** (CPU dev laptop ↔ RTX 1050 box)
via an **admin, runtime-toggleable** performance panel — device (GPU/CPU), resolution, and an
optimizer — no rebuild, no config-file editing. Promotes today's import-time env knobs (`USE_GPU`,
`FACE_DET_SIZE`, camera resolution, probe/frame settings) to live, persisted settings.

## Locked decisions
- **Hot-apply (live reload)**: a change pauses perception ~1–2 s, rebuilds the model on the new
  device/resolution, and resumes; in-flight recognition drained first, taps buffered across the gap.
- **Optimizer = all three**: an **"Optimize for this machine" button** (detect + benchmark + apply),
  **manual presets** (Quality / Balanced / Fast), and an **adaptive auto-tune** loop (optional).
- **Resolution UI = presets + advanced**: Low/Med/High (bundles camera res + `FACE_DET_SIZE`) with an
  advanced section to set each independently.
- **Admin-only** (roles, Step 35). Infra values (DB DSN, SMTP creds) stay **env-only** — not runtime.

## Config precedence (new)
`DB settings override  >  env default (.env)  >  code default`. Only the **tunable perf/device/
resolution** set is DB-overridable; everything else keeps the current env-driven behavior. Single
backend worker (design-notes §3) means one settings cache + one model instance to reload — required.

## Progress summary (tuning)
- [x] Step 50 — Runtime settings layer — `backend/schema.sql` (`settings` table), `backend/settings.py` (typed getter, DB > env > default, tunable keys whitelist), `main.py` (`GET /api/settings`, `PUT /api/settings`). Verified live: set value persists across restart.
- [ ] Step 51 — Model hot-reload (pause/drain/rebuild/resume)
- [ ] Step 52 — Device toggle + resolution controls (backend/API)
- [ ] Step 53 — Optimizer (button + presets + adaptive)
- [x] Step 54 — Settings/optimizer UI panel — `frontend/src/pages/Settings.tsx` (editable tunable keys, collapsible full dump). Basic version; optimizer button + device picker deferred to Steps 51–53.

---

## Step 50 — Runtime settings layer
**Goal**: live, persisted, admin-tunable settings with clear precedence.
**Depends on**: DB; roles (Step 35) for write-gating.
Tasks:
- [ ] `settings` key/value table (+ idempotent migration); `backend/settings.py` typed getters that
      return the **effective** value (DB → env → default), with an in-process cache + invalidation.
- [ ] Define the **tunable set**: device (auto/gpu/cpu), camera resolution, `FACE_DET_SIZE`,
      `MIN_FACE_PX`, probe/frame-skip, `ASSOC_WINDOW_SEC`. Everything else stays env-only.
- [ ] Read paths in `face.py` / `liveness.py` / perception use `settings.get(...)` not raw env.
**Acceptance**: set a value via API → effective value changes and **persists across restart**;
non-tunable/infra keys are rejected.

## Step 51 — Model hot-reload
**Goal**: swap device/resolution on a live pipeline without a crash or a restart.
**Depends on**: Step 50; perception (Flow Step 30).
Tasks:
- [ ] `face.reload()` / `liveness.reload()`: drop cached `_app` / `_sessions`, rebuild from current
      settings. Camera-resolution change = release + reopen `VideoCapture`; det_size/device = rebuild model.
- [ ] Perception coordinator: **pause capture → drain in-flight recognition → reload → resume**; taps
      during the gap are buffered (matcher window absorbs ~1–2 s).
- [ ] **Fail-safe**: reload error (e.g. force-GPU, no CUDA) → fall back to CPU, surface the error,
      keep running (never leave the pipeline dead).
**Acceptance (sim)**: trigger a reload on the video-file perception harness → brief pause, correct new
device/session, no crash, buffered taps still resolve.

## Step 52 — Device toggle + resolution controls
**Goal**: the actual knobs behind the panel, with guards.
**Depends on**: Steps 50–51.
Tasks:
- [ ] Device setting **Auto / Force GPU / Force CPU**; `gpu_runtime()` reads the effective setting
      (keeps auto CPU-fallback). Report **detected GPU + current effective device** to the UI.
- [ ] Resolution: camera capture W×H + `FACE_DET_SIZE`; **Low/Med/High** preset map + advanced
      independent values. Report the **actually applied** camera res (devices may not honor a request).
- [ ] Guards: warn/prevent High-on-CPU footguns; validate ranges.
- [ ] Endpoints: `GET/PUT /api/settings`, `GET /api/settings/capabilities` (GPU present, cores, cam modes).
**Acceptance**: switch device/res via API → hot-reload → effective config + capabilities reported;
force-GPU with no CUDA reports the fallback rather than failing.

## Step 53 — Optimizer (button + presets + adaptive)
**Goal**: make good settings automatic — critical for the install-anywhere / non-technical goal.
**Depends on**: Step 52; metrics (Backbone Step 22); overlaps Flow Step 32 (GPU perf work).
Tasks:
- [ ] **Optimize button**: detect GPU + cores; short **benchmark** (time N recognitions across
      candidate device/res configs on a sample) → pick + apply the recommended profile; show the result.
- [ ] **Presets**: Quality / Balanced / Fast bundling device + resolution + probe + frame-skip.
- [ ] **Adaptive auto-tune** (toggleable): controller monitors fps/latency vs a target; steps
      resolution/frame-skip **down** under target, **up** with headroom; **hysteresis** to avoid
      flapping; bounded by Step 52 guards; logs each change.
**Acceptance (sim)**: benchmark picks a config on a known fake machine; presets apply; the adaptive
loop lowers resolution on a simulated fps drop and recovers on headroom, without flapping.

## Step 54 — Settings / optimizer UI panel
**Goal**: the admin-facing surface for all of the above.
**Depends on**: SPA (UI Step 12), Steps 50–53.
Tasks:
- [x] Basic settings page: editable tunable keys (`frontend/src/pages/Settings.tsx`), fetches
      `GET /api/settings`, saves via `PUT /api/settings`, collapsible full settings dump.
- [ ] Device picker (Auto/GPU/CPU + shows detected GPU), resolution presets + advanced.
- [ ] **"Optimize for this machine"** button (shows benchmark result), adaptive toggle +
      target fps, and a **live readout** (current fps, latency, device, applied resolution).
- [ ] Hot-apply feedback: show the ~1–2 s reload state; confirm the new effective config.
**Acceptance (sim)**: panel changes device/res and reflects the new effective config + live fps;
optimize button round-trips; adaptive toggle visibly engages.

## Tuning-track deferred (needs real hardware)
- Real GPU↔CPU hot-swap timing + benchmark numbers on the RTX 1050; camera-mode enumeration on the
  actual webcam; adaptive tuning against real load. Logic is built + simulation-tested before then.
