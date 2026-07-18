# Design notes — assumptions, constraints, failure modes, edge cases

Cross-cutting decisions that don't belong to a single build step. Read this **before building
Track 30–35** (the continuous-flow guardpost) — it records the constraints and failure behaviors
that are easy to get silently wrong. Companion to [`../ROADMAP.md`](../ROADMAP.md).

Status: **decisions on record + open questions**, not yet all implemented. Each item says whether
it's decided or still open.

---

## 1. Assumptions
- **Population**: children at a controlled kiosk; they stop and face the camera. Faces are close
  and roughly frontal. (Recognition accuracy on children is *worse* than on adults — see §7.)
- **Deployment**: one guardpost, one backend host. Prod target = **RTX 1050 GPU box**; the current
  4-core CPU laptop is a **~1 student/s dev demo only**.
- **Trust boundary**: the Arduino is relay-only (no decisions on-device); all identity/verification
  logic is on the backend. LAN is semi-trusted (see §6).
- **Scale**: hundreds of enrolled students, not tens of thousands (affects 1:N index choices).

## 2. Non-goals (explicit — don't build these unless re-scoped)
- Not a general access-control / door-lock system (attendance logging only; Arduino drives no relay lock).
- Not multi-site / multi-tenant (single guardpost, single DB).
- Not cardless *presence* — cardless 1:N exists **only** to name tailgaters (§ROADMAP Step 33).
- No 3D-mask / high-end presentation-attack defense (passive liveness catches photo/replay, not masks).
- No external SSO / identity provider — roles via a local `operators` table.

## 3. Hard constraints (violating these causes silent bugs)
- **Single camera owner.** Only one process may open `/dev/video0`. The perception service
  (ROADMAP Step 30) owns it; `capture_probe()`-style per-tap opens and `preview.py` must not run
  against the same camera concurrently. Everything else subscribes to its published streams.
- **Single backend worker (or shared state).** The tap buffer + events bus live in process memory.
  Running uvicorn with `--workers >1` splits taps and face-events across processes and correlation
  **fails invisibly**. Decision: **pin one worker**; if horizontal scale is ever needed, externalize
  the buffer/bus to Redis. Document `--workers 1` in the systemd unit / compose.
- **Reader throughput ceiling.** One RC522 on a **9600-baud** serial link cannot reliably sustain
  3–5 taps/s (UID read + anti-collision + framing ≈ 100–300 ms/card; 9600 baud ≈ 1 ms/byte). The
  3–5/s target assumes **either** a higher baud + faster read loop **or multiple readers** with a
  `door_id`. **Open**: pick one before promising burst throughput. Raise `SERIAL_BAUD` regardless.
- **Shared clock for correlation.** Tap timestamps and face-event timestamps must come from the
  **same host clock** (they do — both on the backend). Beware serial-buffering delay between the
  physical tap and the `/tap` POST; keep `ASSOC_WINDOW_SEC` (default 4 s) wider than that delay.
- **GPU for throughput.** 3–5/s requires `onnxruntime-gpu` + face tracking (recognition once per
  track). On CPU the pipeline is correct but slow.

## 4. Failure-mode → behavior table (decided unless marked open)
| Failure | Behavior | Notes |
|---|---|---|
| No camera at startup | Card-only log, `status=unverified`, notify warns | Existing fail-open. |
| **Camera dies mid-shift** | Card-only, `status=unverified` (**not** `present`) + **loud operator alert** | **Decision**: degraded mode must be visible — silent fallback = buddy-punch window. |
| Perception process crash | Same as camera-dead + auto-restart (systemd) | Bounded restart loop. |
| Postgres unreachable | Reader queues taps (`failed_taps.jsonl`); matcher retries; local roster cache verifies | Extends existing queue (Backbone Step 22). |
| Recognition backpressure (faces > throughput) | **Bounded** queue, drop oldest frames, keep newest face per track | Never grow memory unbounded. |
| Duplicate/held-card reads | Debounce within `TAP_COOLDOWN_SEC` | ROADMAP Step 31/23. |
| Tap, no matching face in window | `flagged: no-face` → review queue | Student pulled aside. |
| Face below threshold for its tap | `flagged: mismatch` → review | Possible buddy-punch or bad capture. |
| Face matching no tap | `tailgating` + cardless whole-DB name lookup → alert + review | Never marked present. |
| Liveness fail on matched face | `flagged: spoof` → review | Photo/replay attempt. |
| SMTP / webhook down | Caught, logged; tap unaffected | Existing fail-open (Step 8). |

## 5. Correlation edge-case rules (the matcher, Step 31)
- **Overlap bleed**: bursts make a tap's window overlap the next student's. Mitigate with
  (a) **top1−top2 margin** on the assignment (reject ambiguous), (b) prefer the *temporally
  closest* tap↔face pair, (c) **open**: add a spatial cue (which face was near the reader) if
  time+embedding proves insufficient in testing.
- **Lookalikes / siblings**: high cosine to the wrong tapped student. Margin gate + review; consider
  a per-student threshold for known-similar pairs.
- **Count mismatch**: N taps, M faces. Assign the min(N,M) best pairs above threshold+margin; leftover
  taps → `no-face`, leftover faces → `tailgating`.
- **Order independence**: tap-before-face and face-before-tap both resolve within the window.

## 6. Security & privacy (implementation-affecting)
- **Embeddings are permanent PII.** A face template can't be reset like a password; a DB leak is
  forever. → encryption at rest (Backbone Step 20) is higher-priority here than typical apps.
- **Stream auth.** The admin dashboard + WS are token-gated. The **public viewer** shows boxes +
  status only, **no names** (decided) — but its MJPEG/annotated stream is still kids' faces; keep it
  **LAN-only + consider TLS**, and don't expose it beyond the guardpost network.
- **Operator token** is a shared secret → rotation plan; promote to per-user `operators` accounts
  (Step 35). Audit log (Step 20) should be append-only / tamper-evident where feasible.
- **No images on disk** invariant stays: enrollment frames → embedding → discarded.

## 7. Legal & ethical (children's biometrics — gate before real deployment)
- **Special-category data.** Minors' biometrics fall under GDPR Art. 9 / COPPA (<13) / Illinois BIPA
  and similar. Guardian **consent is typically mandatory and revocable** → consent is a **hard gate**
  on enrollment + matching (Backbone Step 20), not optional. A **DPIA** is expected.
- **Non-biometric fallback required.** Guardians who decline face processing must still get their
  child marked present by card alone (`FACE_MATCH_ENABLED` per-student, not just global).
- **Bias.** Recognition error is higher and uneven for children and across skin tones. → measure
  per-group error (§8); don't ship a single global threshold as "fair".
- **Model license.** InsightFace `buffalo_l` pretrained pack is **non-commercial research** (see
  `NOTICE`). A school deployment may or may not count as commercial — **get clarity before going
  live**; be ready to swap to a commercially-licensed model (hence `embed_model` tagging, Step 33).

## 8. Accuracy evaluation methodology (before tuning thresholds for real)
- Build a small **labeled eval set**: genuine pairs (same person, different day/lighting) + impostor
  pairs (different people, incl. sibling/lookalike pairs), captured on the *actual* kiosk camera.
- Compute **FAR/FRR** across cosine thresholds → pick the operating point; record the curve.
- Re-run when the model (`embed_model`) or camera changes. `backend/calibrate.py` is the starting
  point (currently distribution-only; extend to FAR/FRR).
- **Open**: define the target operating point (e.g. FAR ≤ 0.1% at the kiosk) with the stakeholder.

## 9. Edge-case checklist (build/test reference)
Cards/HW: held-card repeat reads · two cards in field · lost/reissued card (UID remap) · backlighting ·
camera fails mid-shift · raise baud / multi-reader.
Correlation: taps≠faces · tap-then-leave · legit student mis-flagged as tailgater · clock/serial skew.
Data: per-tap vs per-day attendance unit (double counting) · day-boundary/DST · `embed_model` backfill ·
bounded queues.
Ops/human: bulk enrollment (whole school) · review-queue overload at rush · visitors/substitutes ·
camera height for short/tall/wheelchair.
Security: embedding theft · stream auth/TLS · token rotation · audit tamper.

## 10. Open decisions (owner: stakeholder + build)
1. Reader strategy: higher baud on one reader **vs** multiple readers + `door_id`? (blocks real burst throughput)
2. Attendance unit: per-tap log vs per-student-per-day roll-up?
3. Accuracy target (FAR/FRR operating point) for this population?
4. Consent/legal jurisdiction + is the school use "commercial" for the model license?
5. Camera-dead degraded mode: log as `unverified` (recommended) vs block taps entirely?
