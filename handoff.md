# Handoff — UI-only surfaces over existing endpoints

**STATUS: Tasks 1–9 built and verified (`make web-build` passes). Task 10 (polish) deferred.**

**For the implementing agent.** Build these frontend surfaces. Every one consumes a
backend endpoint that **already exists and works** — so this is a pure-frontend job.

## Hard rules (read first)

1. **Do NOT edit any backend file.** No changes to `backend/*.py`, `backend/schema.sql`,
   `requirements.txt`, or the DB. If you think you need a backend change, stop and flag it
   — it means the task was mis-scoped. The only files you touch are under `frontend/src/`
   (plus optional docs).
2. **Graphify first.** This repo mandates it: before exploring code, run
   `graphify query "<question>"`; only read raw files after. After finishing, run
   `graphify update .`.
3. **Conventions already in the repo — match them exactly** (see next section). Don't invent
   a new styling system, state library, or fetch wrapper.
4. **Privacy rule (non-negotiable):** the public **Viewer** shows boxes + status only —
   **no student names, no PII**. Operator-only pages may show names.
5. Verify each surface with the running backend (`http://localhost:8001/app`) and a
   `make web-build` before calling it done. Do not claim live-camera verification — that
   needs hardware and is out of scope.

## Project conventions (use these, don't reinvent)

- **Stack:** Vite + React 18 + TypeScript. Pages in `frontend/src/pages/`, shared bits in
  `frontend/src/components/`. Existing pages: `Dashboard, Kiosk, Roster, Register, Review,
  Settings`. Existing components: `TodayPanel, LiveFeed, HistoryTable, CameraFeed`.
- **API client:** `frontend/src/api.ts`. Reuse its helpers — do not call `fetch` directly
  in components:
  - `req<T>(path)` — GET, JSON in/out, auto-adds `X-Operator-Token` when a token is set.
  - `reqJson<T>(path, method, body)` — POST/PUT/PATCH with JSON body.
  - `del<T>(path)` — DELETE.
  - `postFormData<T>(path, formData)` — multipart POST (adds the token header, no
    Content-Type override).
  - `getToken()` / `setToken()` — operator token in `localStorage` (`operator_token`).
  - **Two helpers you must ADD to `api.ts`** (they don't exist yet — needed for CSV + metrics):
    ```ts
    export async function reqBlob(path: string): Promise<Blob> {
      const token = getToken()
      const headers: Record<string, string> = {}
      if (token) headers['X-Operator-Token'] = token
      const res = await fetch(path, { headers })
      if (!res.ok) throw new Error(`${path} -> ${res.status}`)
      return res.blob()
    }
    export async function reqText(path: string): Promise<string> {
      const token = getToken()
      const headers: Record<string, string> = {}
      if (token) headers['X-Operator-Token'] = token
      const res = await fetch(path, { headers })
      if (!res.ok) throw new Error(`${path} -> ${res.status}`)
      return res.text()
    }
    ```
- **Auth model:** all `/api/*` require the operator token **iff** `OPERATOR_TOKEN` is set on
  the backend (unset = open dev mode). The `req*` helpers handle it. `/health`,
  `/stream.mjpeg`, and the `/kiosk` route are **public** (no token). New operator pages must
  be gated the same way existing ones are (hidden behind `authed` in the nav — see below).
- **Routing/nav:** `frontend/src/App.tsx`. Operator pages are `<NavLink>`s wrapped in
  `{authed && …}`; public pages (Kiosk) are always shown. Add each new route to both the
  `<nav>` and `<Routes>`. `authed` reacts to a `window` `'auth-changed'` event — dispatch it
  after `setToken` if you add a login control (Dashboard already owns login).
- **CSS utility classes (already defined in `frontend/src/index.css`):** `.wrap`, `.page`,
  `.card`, `.nav`, `.spacer`, `.pill`, `.dash-grid`, `.btn`, `.btn-sm`, `.btn-ghost`,
  `.btn-danger`, `.active`. Reuse them. For status color pills, **copy the existing pattern
  from `components/LiveFeed.tsx` / `TodayPanel.tsx`** (status → color) rather than defining a
  new scheme. Add new classes to `index.css` only if genuinely needed.
- **Types:** extend `api.ts` with the interfaces below; several (`AuditEntry`, `Student`,
  `TapLog`, `Config`, `StatsToday`, `Health`) already exist — reuse them.
- **Build/run:** `make web-build` then hard-refresh `http://localhost:8001/app`. Dev loop:
  `make web-dev` → `http://localhost:5173/app/`. Backend runs via
  `systemctl --user restart nfc-scan-backend`.

---

## Task 1 — Public boxes-only Viewer (highest value) — DONE

- **Route:** `/viewer` — **public** (place OUTSIDE the `authed` guard, next to `/kiosk`).
- **File:** `frontend/src/pages/Viewer.tsx`.
- **Endpoint:** `GET /stream.mjpeg` — public, no token. It's an
  `multipart/x-mixed-replace` MJPEG stream of annotated frames (green/amber boxes + track
  IDs). Render with a plain `<img src="/stream.mjpeg" />` (no fetch needed).
- **Behavior:** fullscreen `<img>` of the stream, a title/idle caption, and nothing else.
  **No names, no scores, no PII** — boxes only. Optionally show connection state by handling
  the `<img>` `onerror`/`onload`. Reference `components/CameraFeed.tsx` for the existing
  pattern (but strip anything operator-specific).
- **Nav:** add `<NavLink to="/viewer">Viewer</NavLink>` in the always-visible group (like
  Kiosk).
- **Acceptance:** `/app/viewer` shows the live boxes stream when `PERCEPTION_ENABLED=true`
  (default) and a camera is present; shows a graceful "camera offline" state otherwise; no
  student names anywhere on the page.

## Task 2 — Attendance summary (present / absent / late) — DONE

- **Route:** `/summary` (operator). **File:** `frontend/src/pages/Summary.tsx`.
- **Endpoint:** `GET /api/attendance/summary?date=YYYY-MM-DD` (date optional → today).
- **Response shape (exact):**
  ```ts
  interface AttendanceSummary {
    date: string
    expected: number
    present: { student_id: string; name: string | null; late: boolean }[]
    absent:  { student_id: string; name: string | null }[]
    late_count: number
    late_cutoff: string | null   // "HH:MM:SS" or null if LATE_CUTOFF unset
  }
  ```
- **api.ts:** `export const getSummary = (date?: string) =>
  req<AttendanceSummary>(\`/api/attendance/summary\${date ? \`?date=\${date}\` : ''}\`)`
- **Behavior:** a date picker (defaults today); three cards — Present (with a "late" badge on
  late rows), Absent, and a headline (`present.length`/`expected`, `late_count`). Empty/
  loading/error states.
- **Acceptance:** picking a date shows present/absent/late correctly; matches the JSON at
  `curl /api/attendance/summary`.

## Task 3 — Sessions view (check-in / check-out / duration) — DONE

- **Route:** `/sessions` (operator). **File:** `frontend/src/pages/Sessions.tsx`.
- **Endpoint:** `GET /api/attendance/sessions?student_id=&date=` (both optional).
- **Response shape (exact):**
  ```ts
  interface AttendanceSession {
    student_id: string
    student_name: string | null
    session_date: string          // "YYYY-MM-DD"
    check_in: string              // ISO timestamp
    check_out: string | null      // ISO or null (still in)
    duration_minutes: number | null
  }
  // GET returns: { sessions: AttendanceSession[] }
  ```
- **api.ts:** `export const getSessions = (params: {student_id?: string; date?: string} = {}) => { …URLSearchParams… return req<{sessions: AttendanceSession[]}>(...) }`
- **Behavior:** filter inputs (date, optional student_id), a table: student, date, check-in,
  check-out (or "in progress"), duration. Newest first (backend already sorts).
- **Acceptance:** a student with two taps in a day shows one session with a duration; matches
  the endpoint JSON.

## Task 4 — CSV export button — DONE

- **Where:** add to the **Summary** or **Sessions** page (or the existing Dashboard
  `HistoryTable`) — not a new route.
- **Endpoint:** `GET /api/attendance.csv?date=&status=&student_id=&limit=` → `text/csv`
  download.
- **GOTCHA (must handle):** when `OPERATOR_TOKEN` is set, a plain `<a download>` /
  `window.open` will **401** because it can't send the `X-Operator-Token` header. Use the
  `reqBlob` helper (added above) + an object URL:
  ```ts
  export async function downloadAttendanceCsv(params: Record<string, string | number> = {}) {
    const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()
    const blob = await reqBlob(`/api/attendance.csv${q ? `?${q}` : ''}`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'attendance.csv'; a.click()
    URL.revokeObjectURL(url)
  }
  ```
- **Behavior:** a "Download CSV" button that respects the page's current filters.
- **Acceptance:** clicking downloads `attendance.csv` with the header row
  `id,uid,student_id,student_name,ts,method,status,face_score,face_match,liveness_score,liveness_pass`;
  works both with and without a token set.

## Task 5 — Audit log viewer — DONE

- **Route:** `/audit` (operator). **File:** `frontend/src/pages/Audit.tsx`.
- **Endpoint:** `GET /api/audit?limit=100` (limit 1–1000).
- **Response:** `{ audit: AuditEntry[] }` — `AuditEntry` **already exists** in `api.ts`
  (`{id, ts, actor, action, target, detail}`).
- **api.ts:** `export const getAudit = (limit = 100) => req<{audit: AuditEntry[]}>(\`/api/audit?limit=\${limit}\`)`
- **Behavior:** newest-first table (ts, actor, action, target, detail). Color the `action`
  (`enroll` / `consent` / `erase` / `review_resolve`) with a pill. A limit selector.
- **Acceptance:** performing an enroll/consent/delete elsewhere adds a row here after reload.

## Task 6 — Re-enrollment reminders panel — DONE

- **Route:** `/reenroll` (operator), or a panel on Roster. **File:**
  `frontend/src/pages/Reenroll.tsx` (or a component).
- **Endpoint:** `GET /api/reenroll-due`.
- **Response shape (exact):**
  ```ts
  interface ReenrollDue {
    reenroll_after_days: number
    current_model: string
    due: { student_id: string; name: string | null; embed_model: string | null; enrolled_at: string | null }[]
  }
  ```
- **api.ts:** `export const getReenrollDue = () => req<ReenrollDue>('/api/reenroll-due')`
- **Behavior:** show `current_model` + `reenroll_after_days`, then a table of due students
  (student, current embed_model, enrolled_at). Note in the UI that a null `embed_model` means
  the student predates provenance tracking. Optionally link each row to `/register`.
- **Acceptance:** lists students whose `embed_model` differs from `current_model` or whose
  `enrolled_at` is older than the window (S001 will appear).

## Task 7 — Manual face lookup (cardless 1:N) — DONE

- **Route:** `/lookup` (operator). **File:** `frontend/src/pages/Lookup.tsx`.
- **Endpoint:** `POST /api/search-face?k=5` — **multipart**, single field `image` (one file).
  Returns nearest enrolled students. **No image is stored server-side.**
- **Response shape (exact):**
  ```ts
  interface FaceMatch { student_id: string; name: string | null; uid: string; similarity: number }
  // POST returns: { matches: FaceMatch[] }
  // 400 if the image can't be decoded; 422 if no usable face (>= MIN_FACE_PX).
  ```
- **api.ts:**
  ```ts
  export const searchFace = (file: File, k = 5) => {
    const fd = new FormData(); fd.append('image', file)
    return postFormData<{ matches: FaceMatch[] }>(`/api/search-face?k=${k}`, fd)
  }
  ```
- **Behavior:** a file input (accept `image/*`; optionally also `getUserMedia` capture like
  `Register.tsx`), a "Search" button, and a ranked results table (student, uid, similarity as
  a %). Handle 400/422 with a friendly message ("no usable face in image").
- **Acceptance:** uploading a photo of an enrolled student returns them at the top with a high
  similarity; a face-less image shows the 422 message.

## Task 8 — Ops / health readout — DONE

- **Route:** `/ops` (operator) or a Settings panel. **File:** `frontend/src/pages/Ops.tsx`.
- **Endpoints (all exist):**
  - `GET /health` → `{status, db}` (public) — use existing `getHealth()`.
  - `GET /api/stats/today` → `StatsToday` — use existing `getStatsToday()`.
  - `GET /api/config` → `Config` — use existing `getConfig()` (shows perception/privacy/face
    flags).
  - `GET /metrics` → **Prometheus text, not JSON.** Use the `reqText` helper and show it in a
    `<pre>` (don't try to parse it). Optional.
- **Behavior:** health pill, today's counts (reuse `TodayPanel` if convenient), a read-only
  dump of `config`, and optionally the raw metrics text. Poll `/health` every ~10s.
- **Acceptance:** shows live DB health + today's status counts + active config flags.

## Task 9 — Kiosk audio cues (frontend-only, no endpoint) — DONE

- **File:** `frontend/src/pages/Kiosk.tsx` (already exists — the verdict screen).
- **Behavior:** on a tap verdict, play a short sound — accept chime for `accepted`, a buzz for
  `rejected`/`spoof`/`mismatch`. Generate tones with the Web Audio API (no external assets, no
  network) so nothing is bundled. Respect a mute toggle; autoplay only after a user gesture
  (kiosk operator clicks once to "arm sound").
- **Acceptance:** POSTing `/tap` for an accepted vs rejected student plays distinct sounds;
  muted by default until armed.

## Task 10 — Polish (optional, do last)

- README screenshots/GIF of Dashboard + Kiosk + Viewer; consistent empty/loading/error states
  across the new pages; responsive check (nav wraps, tables scroll in `overflow-x:auto`).
- **No backend, no CORS/token changes** — those are Step 16 and belong to a different handoff.

---

## Suggested order

1. Task 1 (Viewer) — highest value, smallest.
2. Tasks 2–4 (Summary, Sessions, CSV) — surfaces the whole Step 21 layer.
3. Tasks 5–7 (Audit, Reenroll, Lookup) — makes the Step 20/33 compliance work usable.
4. Tasks 8–9 (Ops, Kiosk audio). 5. Task 10 (polish).

## Definition of done (every task)

- New/changed files only under `frontend/src/` (+ optional `README.md`). **Zero backend
  edits.**
- Route added to `App.tsx` nav (operator pages behind `authed`; Viewer public).
- New endpoint calls go through `api.ts` helpers, never raw `fetch` in a component.
- `make web-build` succeeds; the page renders at `http://localhost:8001/app/<route>` against
  the running backend; empty/loading/error states handled.
- Run `graphify update .` at the end.
