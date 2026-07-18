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

## Progress summary
- [ ] Step 10 — One-command setup (foundation)
- [ ] Step 11 — Backend API expansion + live tap stream
- [ ] Step 12 — Frontend scaffold (SPA toolchain)
- [ ] Step 13 — Operator dashboard (read views)
- [ ] Step 14 — Roster + browser enrollment (write views)
- [ ] Step 15 — Kiosk feedback screen
- [ ] Step 16 — Hardening & polish (auth, docs, screenshots)

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
