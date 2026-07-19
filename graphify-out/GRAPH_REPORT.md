# Graph Report - nfc-scan  (2026-07-20)

## Corpus Check
- 67 files · ~44,767 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 674 nodes · 941 edges · 67 communities (51 shown, 16 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 8 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e0b21af6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Face Verification (buffalo_l)|Face Verification (buffalo_l)]]
- [[_COMMUNITY_Liveness  Anti-Spoof (MiniFASNet)|Liveness / Anti-Spoof (MiniFASNet)]]
- [[_COMMUNITY_Roadmap UI & Tuning Tracks|Roadmap: UI & Tuning Tracks]]
- [[_COMMUNITY_Roadmap Flow Track (Guardpost)|Roadmap: Flow Track (Guardpost)]]
- [[_COMMUNITY_Decision & 2FA Enforcement|Decision & 2FA Enforcement]]
- [[_COMMUNITY_Serial Reader & Arduino Relay|Serial Reader & Arduino Relay]]
- [[_COMMUNITY_Face Enrollment|Face Enrollment]]
- [[_COMMUNITY_Backbone Privacy & DB Schema|Backbone: Privacy & DB Schema]]
- [[_COMMUNITY_Postgres Data Layer|Postgres Data Layer]]
- [[_COMMUNITY_Threshold Calibration|Threshold Calibration]]
- [[_COMMUNITY_USB Webcam Device|USB Webcam Device]]
- [[_COMMUNITY_Env-Driven Config Principle|Env-Driven Config Principle]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]

## God Nodes (most connected - your core abstractions)
1. `get_conn()` - 29 edges
2. `compilerOptions` - 17 edges
3. `Dual-Factor Attendance System (nfc-scan)` - 16 edges
4. `req()` - 15 edges
5. `Handoff — UI-only surfaces over existing endpoints` - 15 edges
6. `Matcher` - 13 edges
7. `Flow track (Steps 30–35) — continuous multi-student guardpost` - 13 edges
8. `getToken()` - 12 edges
9. `Face verification (Step 6) — runbook` - 12 edges
10. `Design notes — assumptions, constraints, failure modes, edge cases` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Flow track (Steps 30-35) continuous guardpost` --semantically_similar_to--> `Locked architecture (Arduino relay -> FastAPI -> Postgres)`  [INFERRED] [semantically similar]
  ROADMAP.md → README.md
- `Camera-dead degraded mode (unverified + alert)` --conceptually_related_to--> `Fail-open principle`  [EXTRACTED]
  docs/design-notes.md → README.md
- `Python requirements` --references--> `InsightFace buffalo_l (ArcFace R50, 512-d)`  [INFERRED]
  requirements.txt → README.md
- `Flow track (Steps 30-35) continuous guardpost` --references--> `Design notes (constraints, failure modes, edge cases)`  [EXTRACTED]
  ROADMAP.md → docs/design-notes.md
- `Tap-face correlation edge-case rules` --rationale_for--> `Step 31 Tap buffer + tap-face correlation (matcher)`  [EXTRACTED]
  docs/design-notes.md → ROADMAP.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Per-tap 1:1 verification flow (face + liveness + decision + notify)** — backend_face, backend_liveness, backend_decision, backend_notify, db_attendance_logs [EXTRACTED 1.00]
- **Fail-open principle across modules** — readme_failopen, backend_face, backend_liveness, backend_notify, backend_decision [EXTRACTED 1.00]
- **Flow track continuous perception + correlation** — roadmap_step30, roadmap_step31, designnotes_single_camera_owner, designnotes_single_backend_worker, designnotes_correlation [EXTRACTED 1.00]

## Communities (67 total, 16 thin omitted)

### Community 0 - "Face Verification (buffalo_l)"
Cohesion: 0.18
Nodes (14): capture_probe(), detect(), embed(), encode_image(), get_app(), largest_usable(), open_capture(), Run recognition on a single detected face -> normed 512-d embedding. (+6 more)

### Community 1 - "Liveness / Anti-Spoof (MiniFASNet)"
Cohesion: 0.15
Nodes (16): gpu_runtime(), (ctx_id, providers) honoring USE_GPU, with automatic CPU fallback.      Shared s, assess(), calibrated(), _crop(), _get_new_box(), get_sessions(), Passive liveness / anti-spoofing (Step 7). MiniFASNet ensemble via onnxruntime. (+8 more)

### Community 3 - "Roadmap: UI & Tuning Tracks"
Cohesion: 0.18
Nodes (10): CamSource, is, SetupWizard(), EnrollResult, getPerceptionState(), getSetupStatus(), getToken(), PerceptionState (+2 more)

### Community 4 - "Roadmap: Flow Track (Guardpost)"
Cohesion: 0.06
Nodes (44): flush_queue(), main(), open_serial(), post_tap(), queue_failed_tap(), pgvector face_embedding vector(512), students table, Children's biometrics legal/consent gate (+36 more)

### Community 5 - "Decision & 2FA Enforcement"
Cohesion: 0.12
Nodes (18): _camera_frames(), _emit(), enabled(), FaceTracker, _iou(), main(), on_frame(), process_frame() (+10 more)

### Community 6 - "Serial Reader & Arduino Relay"
Cohesion: 0.20
Nodes (10): Carried-over deferred items (from Steps 7–9, still open), Cross-cutting definition of done (every phase), Step 10 — One-command setup (foundation), Step 11 — Backend API expansion + live tap stream, Step 12 — Frontend scaffold (SPA toolchain), Step 13 — Operator dashboard (read views), Step 14 — Roster + browser enrollment (write views), Step 15 — Kiosk feedback screen (+2 more)

### Community 7 - "Face Enrollment"
Cohesion: 0.13
Nodes (8): Matcher, PendingFace, PendingTap, Tap ↔ face correlation (Step 31, Flow track).  A tap identifies a student (NFC), Buffer a tap. Returns its id, or None if debounced (held/duplicate card, Sink for perception face events (register via perception.on_face)., Resolve every tap whose window has closed and every unclaimed ripe face., Optimal (Hungarian) tap->face assignment. Only time-valid pairs (within

### Community 8 - "Backbone: Privacy & DB Schema"
Cohesion: 0.06
Nodes (51): delete_student(), find_duplicate(), find_student_by_uid(), get_all_settings(), get_attendance(), get_attendance_csv(), get_audit(), get_conn() (+43 more)

### Community 9 - "Postgres Data Layer"
Cohesion: 0.12
Nodes (16): Architecture (locked), Docs map, Dual-Factor Attendance System (nfc-scan), Face verification (Step 6), Hardware, License, Liveness, guardian email & enforcement (Steps 7–9), Not production-ready (before any real deployment) (+8 more)

### Community 10 - "Threshold Calibration"
Cohesion: 0.15
Nodes (12): Camera preview (setup aid), Configuration (env vars), Enrollment, Face verification (Step 6) — runbook, Hardware, How a tap verifies, Known limitation, Performance & GPU (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (11): HIGHLIGHT, STATUS_COLORS, Dashboard(), Kiosk(), Verdict, VS, Register(), Health (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (12): 10. Open decisions (owner: stakeholder + build), 1. Assumptions, 2. Non-goals (explicit — don't build these unless re-scoped), 3. Hard constraints (violating these causes silent bugs), 4. Failure-mode → behavior table (decided unless marked open), 5. Correlation edge-case rules (the matcher, Step 31), 5a. Adaptive / late-bind resolution (planned refinement — NOT yet built), 6. Security & privacy (implementation-affecting) (+4 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (10): Deferred (needs hardware), Regression — sync 1:1 flow still works (perception off), Step 10 — one-command setup, Step 11 — operator API + live tap stream, Step 12 — SPA scaffold, Step 20 — privacy / consent / audit / retention, Step 30 — perception service `[GPU/HW]` (logic verified on CPU), Step 31 — tap↔face matcher `[CPU]` (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (7): AbstractEventLoop, publish(), Any, Tiny in-process pub/sub for live tap events (Step 11).  `/tap` is a sync FastAPI, Record the running event loop (called once at startup)., Broadcast an event to all subscribers. Safe to call from any thread., set_loop()

### Community 17 - "Community 17"
Cohesion: 0.33
Nodes (5): Build order (from original spec), Build status & where things live (Steps 10+), Dev environment specifics, nfc-scan — project context, Other Postgres/Docker instances on this machine (do not touch)

### Community 18 - "Community 18"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleDetection, moduleResolution (+11 more)

### Community 19 - "Community 19"
Cohesion: 0.11
Nodes (18): dependencies, react, react-dom, react-router-dom, devDependencies, @types/react, @types/react-dom, typescript (+10 more)

### Community 20 - "Community 20"
Cohesion: 0.07
Nodes (27): _check(), System health check (Step 22).  Usage:     python -m backend.doctor  Checks ever, run(), average_reference(), enroll_student(), _from_capture(), _from_images(), main() (+19 more)

### Community 21 - "Community 21"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (13): Conflicts this track resolves (current code that must change), Flow-track deferred items (need GPU box / live cam / kiosk), Flow track (Steps 30–35) — continuous multi-student guardpost, Locked decisions (from design review), Open defaults (proceeding unless changed), Prerequisites (from other tracks — do first), Progress summary (flow), Step 30 — Perception service (single camera owner) (+5 more)

### Community 27 - "Community 27"
Cohesion: 0.29
Nodes (5): is, AttendanceSummary, downloadAttendanceCsv(), getSummary(), reqBlob()

### Community 28 - "Community 28"
Cohesion: 0.25
Nodes (7): Audit log, Consent gate, Not yet done, Privacy & data handling (Step 20), Retention & purge, Right to erasure, What is stored

### Community 29 - "Community 29"
Cohesion: 0.19
Nodes (16): _digest_body(), _digest_for_student(), Guardian attendance digest (Step 21).  Sends a batched daily summary email to ea, Build a digest email body for one student. Returns None if there's nothing     t, run(), _build_email(), _console(), _email() (+8 more)

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (15): Definition of done (every task), Handoff — UI-only surfaces over existing endpoints, Hard rules (read first), Project conventions (use these, don't reinvent), Suggested order, Task 10 — Polish (optional, do last), Task 1 — Public boxes-only Viewer (highest value) — DONE, Task 2 — Attendance summary (present / absent / late) — DONE (+7 more)

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (10): Face verification (Step 6, 1:1). InsightFace buffalo_l ArcFace, 512-d.  Detectio, CPU-tuned crowd-independent tap cost, FACE_DET_SIZE detector input size, FACE_THRESHOLD cosine cutoff, USE_GPU switch (face + liveness), Face verification (Step 6) runbook, Live verification record 2026-07-10 (genuine 0.86 / impostor 0.018), RTX 1050 GPU appliance box (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.17
Nodes (10): counts_as_present(), decide(), Attendance verification decision / buddy-punch enforcement (Step 9).  NFC identi, Collapse the per-factor verdicts into one attendance status.      student:, True when the tap should count as attendance. Rejected + the matcher review, ENFORCE_2FA enforcement flag, attendance_logs table, Camera-dead degraded mode (unverified + alert) (+2 more)

### Community 33 - "Community 33"
Cohesion: 0.16
Nodes (15): FormState, is, createStudent(), del(), deleteStudent(), getSettings(), getStudents(), reqJson() (+7 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (11): api_create_student(), api_resolve_review(), api_set_consent(), api_set_settings(), api_update_student(), ConsentRequest, ResolveReview, SettingsUpdate (+3 more)

### Community 35 - "Community 35"
Cohesion: 0.24
Nodes (7): STATUS_COLORS, Config, getConfig(), getHealth(), getStatsToday(), req(), StatsToday

### Community 36 - "Community 36"
Cohesion: 0.15
Nodes (6): ACTION_COLORS, AuditEntry, getAudit(), getReenrollDue(), ReenrollDue, App()

### Community 37 - "Community 37"
Cohesion: 0.50
Nodes (4): main(), Threshold calibration helper (read-only).  Prints the distribution of logged sco, _report(), Accuracy evaluation methodology (FAR/FRR)

### Community 38 - "Community 38"
Cohesion: 0.25
Nodes (7): Build log — what each built step contains (Steps 10+), Camera stream + Register hardening (recent), Data model & responsibility (Phase C), Design-only stubs (not built), Flow track — perception + matcher (Phase B), Foundation (Phase A), UI surfaces (Phase E)

### Community 39 - "Community 39"
Cohesion: 0.33
Nodes (7): _post_log(), Matcher outcome writer (Step 31): log -> notify -> broadcast. Fail-open., notify + broadcast for a synchronously-written log (fail-open on both)., _strip_embedding(), tap(), TapRequest, _write_outcome()

### Community 40 - "Community 40"
Cohesion: 0.40
Nodes (3): C, getReviewQueue(), ReviewQueueItem

### Community 41 - "Community 41"
Cohesion: 0.33
Nodes (4): ALL_STATUSES, STATUS_COLORS, getAttendance(), TapLog

### Community 42 - "Community 42"
Cohesion: 0.67
Nodes (3): _load_reference(), main(), Live camera diagnostic UI (setup aid, not part of the tap flow).  Shows what the

### Community 43 - "Community 43"
Cohesion: 0.40
Nodes (5): embeddings_from_frames(), frames: iterable of BGR ndarrays -> list of usable 512-d embeddings     (frames, api_enroll_student(), api_search_face(), UploadFile

### Community 45 - "Community 45"
Cohesion: 0.40
Nodes (3): is, AttendanceSession, getSessions()

### Community 46 - "Community 46"
Cohesion: 0.67
Nodes (3): main(), Download the MiniFASNet anti-spoofing ONNX weights (Step 7).  Idempotent: skips, _sha256()

### Community 48 - "Community 48"
Cohesion: 0.20
Nodes (10): Config precedence (new), Locked decisions, Progress summary (tuning), Step 50 — Runtime settings layer, Step 51 — Model hot-reload, Step 52 — Device toggle + resolution controls, Step 53 — Optimizer (button + presets + adaptive), Step 54 — Settings / optimizer UI panel (+2 more)

### Community 49 - "Community 49"
Cohesion: 0.29
Nodes (6): Deferred to the real RTX 1050 box, Deploy — appliance provisioning & operations (Steps 40–43), Kiosk auto-start (Step 40), One-command install (Steps 40–41), Services, Updates, backup & recovery (Step 43)

### Community 53 - "Community 53"
Cohesion: 0.20
Nodes (10): Deploy-track deferred (needs the actual box), Deploy track (Steps 40–44) — distribution & one-touch install, Locked decisions, Progress summary (deploy), Reconciliation, Step 40 — Appliance provisioning (one script, per box), Step 41 — Wrap as a downloadable "button", Step 42 — In-UI first-run wizard (no terminal) (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.33
Nodes (6): Backbone track (Steps 20–23), Progress summary (backbone), Step 20 — Privacy & compliance, Step 21 — Attendance sessions + guardian digest, Step 22 — Reliability & operability, Step 23 — Anti-fraud extensions

### Community 55 - "Community 55"
Cohesion: 0.40
Nodes (4): How to use this doc, Locked tech decisions, nfc-scan — build roadmap (Steps 10–54, five tracks), Progress summary

### Community 57 - "Community 57"
Cohesion: 0.33
Nodes (4): enrollStudent(), FaceMatch, postFormData(), searchFace()

### Community 58 - "Community 58"
Cohesion: 0.70
Nodes (4): bad(), ok(), warn(), preflight.sh script

## Knowledge Gaps
- **214 isolated node(s):** `date`, `AbstractEventLoop`, `Any`, `WebSocket`, `backup.sh script` (+209 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Flow track (Steps 30-35) continuous guardpost` connect `Roadmap: Flow Track (Guardpost)` to `Community 20`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `Build sequence (cross-track priority order)` connect `Roadmap: Flow Track (Guardpost)` to `Community 55`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **What connects `Threshold calibration helper (read-only).  Prints the distribution of logged sco`, `Create a new student. Raises ValueError on duplicate student_id or uid.`, `Update student fields (only non-None values). Raises ValueError if not found.` to the rest of the system?**
  _300 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Tap Endpoint & Notify` be split into smaller, more focused modules?**
  _Cohesion score 0.09523809523809523 - nodes in this community are weakly interconnected._
- **Should `Roadmap: Flow Track (Guardpost)` be split into smaller, more focused modules?**
  _Cohesion score 0.05656565656565657 - nodes in this community are weakly interconnected._
- **Should `Decision & 2FA Enforcement` be split into smaller, more focused modules?**
  _Cohesion score 0.12318840579710146 - nodes in this community are weakly interconnected._
- **Should `Face Enrollment` be split into smaller, more focused modules?**
  _Cohesion score 0.13405797101449277 - nodes in this community are weakly interconnected._