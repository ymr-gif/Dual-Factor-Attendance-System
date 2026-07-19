# Graph Report - nfc-scan  (2026-07-19)

## Corpus Check
- 37 files · ~25,850 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 465 nodes · 603 edges · 28 communities (26 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9b4aea9d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Face Verification (buffalo_l)|Face Verification (buffalo_l)]]
- [[_COMMUNITY_Liveness  Anti-Spoof (MiniFASNet)|Liveness / Anti-Spoof (MiniFASNet)]]
- [[_COMMUNITY_Tap Endpoint & Notify|Tap Endpoint & Notify]]
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
- [[_COMMUNITY_Community 28|Community 28]]

## God Nodes (most connected - your core abstractions)
1. `get_conn()` - 17 edges
2. `compilerOptions` - 17 edges
3. `Matcher` - 13 edges
4. `nfc-scan` - 13 edges
5. `Flow track (Steps 30–35) — continuous multi-student guardpost` - 13 edges
6. `Face verification (Step 6) — runbook` - 12 edges
7. `Design notes — assumptions, constraints, failure modes, edge cases` - 11 edges
8. `UI track (Steps 10–16) — one-command setup, API, SPA, dashboard` - 10 edges
9. `Deploy track (Steps 40–44) — distribution & one-touch install` - 10 edges
10. `Tuning track (Steps 50–54) — runtime device/resolution/optimizer panel` - 10 edges

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

## Communities (28 total, 2 thin omitted)

### Community 0 - "Face Verification (buffalo_l)"
Cohesion: 0.08
Nodes (29): main(), Threshold calibration helper (read-only).  Prints the distribution of logged sco, _report(), capture_probe(), detect(), embed(), encode_image(), get_app() (+21 more)

### Community 1 - "Liveness / Anti-Spoof (MiniFASNet)"
Cohesion: 0.07
Nodes (29): counts_as_present(), decide(), Attendance verification decision / buddy-punch enforcement (Step 9).  NFC identi, Collapse the per-factor verdicts into one attendance status.      student:, True when the tap should count as attendance. Rejected + the matcher review, gpu_runtime(), (ctx_id, providers) honoring USE_GPU, with automatic CPU fallback.      Shared s, main() (+21 more)

### Community 2 - "Tap Endpoint & Notify"
Cohesion: 0.07
Nodes (26): api_search_face(), api_set_consent(), ConsentRequest, _post_log(), Matcher outcome writer (Step 31): log -> notify -> broadcast. Fail-open., notify + broadcast for a synchronously-written log (fail-open on both)., Guard /api/* endpoints. Accepts `Authorization: Bearer <t>` or     `X-Operator-T, require_operator() (+18 more)

### Community 3 - "Roadmap: UI & Tuning Tracks"
Cohesion: 0.11
Nodes (22): pgvector face_embedding vector(512), students table, Children's biometrics legal/consent gate, Config precedence (DB > env > code default), Embeddings are permanent PII, Single backend worker constraint, Backbone track (Steps 20-23), Build sequence (cross-track priority order) (+14 more)

### Community 4 - "Roadmap: Flow Track (Guardpost)"
Cohesion: 0.11
Nodes (22): flush_queue(), main(), open_serial(), post_tap(), queue_failed_tap(), Tap-face correlation edge-case rules, Design notes (constraints, failure modes, edge cases), Reader throughput ceiling (RC522 @ 9600 baud) (+14 more)

### Community 5 - "Decision & 2FA Enforcement"
Cohesion: 0.13
Nodes (16): _camera_frames(), _emit(), enabled(), FaceTracker, _iou(), main(), process_frame(), Continuous perception service (Step 30, Flow track).  One long-running process o (+8 more)

### Community 6 - "Serial Reader & Arduino Relay"
Cohesion: 0.05
Nodes (40): Backbone track (Steps 20–23), Carried-over deferred items (from Steps 7–9, still open), Config precedence (new), Cross-cutting definition of done (every phase), Deploy-track deferred (needs the actual box), Deploy track (Steps 40–44) — distribution & one-touch install, How to use this doc, Locked decisions (+32 more)

### Community 7 - "Face Enrollment"
Cohesion: 0.13
Nodes (8): Matcher, PendingFace, PendingTap, Tap ↔ face correlation (Step 31, Flow track).  A tap identifies a student (NFC), Buffer a tap. Returns its id, or None if debounced (held/duplicate card, Sink for perception face events (register via perception.on_face)., Resolve every tap whose window has closed and every unclaimed ripe face., Optimal (Hungarian) tap->face assignment. Only time-valid pairs (within

### Community 8 - "Backbone: Privacy & DB Schema"
Cohesion: 0.10
Nodes (30): delete_student(), find_duplicate(), find_student_by_uid(), get_attendance(), get_audit(), get_conn(), get_stats_today(), get_student() (+22 more)

### Community 9 - "Postgres Data Layer"
Cohesion: 0.14
Nodes (13): Architecture (locked), Face verification (Step 6), Hardware, License, Liveness, guardian email & enforcement (Steps 7–9), nfc-scan, Notes, Roadmap (+5 more)

### Community 10 - "Threshold Calibration"
Cohesion: 0.15
Nodes (12): Camera preview (setup aid), Configuration (env vars), Enrollment, Face verification (Step 6) — runbook, Hardware, How a tap verifies, Known limitation, Performance & GPU (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.17
Nodes (16): Dashboard(), Kiosk(), getAttendance(), getConfig(), getHealth(), getStatsToday(), getStudents(), getToken() (+8 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (11): 10. Open decisions (owner: stakeholder + build), 1. Assumptions, 2. Non-goals (explicit — don't build these unless re-scoped), 3. Hard constraints (violating these causes silent bugs), 4. Failure-mode → behavior table (decided unless marked open), 5. Correlation edge-case rules (the matcher, Step 31), 6. Security & privacy (implementation-affecting), 7. Legal & ethical (children's biometrics — gate before real deployment) (+3 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (10): Deferred (needs hardware), Regression — sync 1:1 flow still works (perception off), Step 10 — one-command setup, Step 11 — operator API + live tap stream, Step 12 — SPA scaffold, Step 20 — privacy / consent / audit / retention, Step 30 — perception service `[GPU/HW]` (logic verified on CPU), Step 31 — tap↔face matcher `[CPU]` (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (7): AbstractEventLoop, Any, publish(), Tiny in-process pub/sub for live tap events (Step 11).  `/tap` is a sync FastAPI, Record the running event loop (called once at startup)., Broadcast an event to all subscribers. Safe to call from any thread., set_loop()

### Community 17 - "Community 17"
Cohesion: 0.33
Nodes (5): Build order (from original spec), Dev environment specifics, nfc-scan — project context, Other Postgres/Docker instances on this machine (do not touch), Planned work — read before building (Steps 10+)

### Community 18 - "Community 18"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleDetection, moduleResolution (+11 more)

### Community 19 - "Community 19"
Cohesion: 0.11
Nodes (18): dependencies, react, react-dom, react-router-dom, devDependencies, @types/react, @types/react-dom, typescript (+10 more)

### Community 20 - "Community 20"
Cohesion: 0.10
Nodes (21): average_reference(), embeddings_from_frames(), enroll_student(), _from_capture(), _from_images(), main(), Enroll a student's face reference (Step 6; core extracted in Step 33).  Averages, frames: iterable of BGR ndarrays -> list of usable 512-d embeddings     (frames (+13 more)

### Community 21 - "Community 21"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (13): Conflicts this track resolves (current code that must change), Flow-track deferred items (need GPU box / live cam / kiosk), Flow track (Steps 30–35) — continuous multi-student guardpost, Locked decisions (from design review), Open defaults (proceeding unless changed), Prerequisites (from other tracks — do first), Progress summary (flow), Step 30 — Perception service (single camera owner) (+5 more)

### Community 28 - "Community 28"
Cohesion: 0.25
Nodes (7): Audit log, Consent gate, Not yet done, Privacy & data handling (Step 20), Retention & purge, Right to erasure, What is stored

## Knowledge Gaps
- **167 isolated node(s):** `AbstractEventLoop`, `Any`, `UploadFile`, `WebSocket`, `name` (+162 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `nfc-scan build roadmap (Steps 10-54)` connect `Roadmap: UI & Tuning Tracks` to `Roadmap: Flow Track (Guardpost)`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `Flow track (Steps 30-35) continuous guardpost` connect `Roadmap: Flow Track (Guardpost)` to `Roadmap: UI & Tuning Tracks`, `Community 20`?**
  _High betweenness centrality (0.158) - this node is a cross-community bridge._
- **Why does `Build sequence (cross-track priority order)` connect `Roadmap: UI & Tuning Tracks` to `Serial Reader & Arduino Relay`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **What connects `Threshold calibration helper (read-only).  Prints the distribution of logged sco`, `Store a student's averaged reference embedding + provenance (Step 33:     embed_`, `Record biometric-consent for a student. Raises if no such student.` to the rest of the system?**
  _232 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Face Verification (buffalo_l)` be split into smaller, more focused modules?**
  _Cohesion score 0.08235294117647059 - nodes in this community are weakly interconnected._
- **Should `Liveness / Anti-Spoof (MiniFASNet)` be split into smaller, more focused modules?**
  _Cohesion score 0.07130124777183601 - nodes in this community are weakly interconnected._
- **Should `Tap Endpoint & Notify` be split into smaller, more focused modules?**
  _Cohesion score 0.06736353077816493 - nodes in this community are weakly interconnected._