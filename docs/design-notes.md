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
- **Distribution & runtime**: the repo is the *install channel* for the GPU box. Target is a
  **dedicated appliance** that **auto-starts into the UI on boot**; a technician provisions it
  **once**, then non-technical staff just power it on. Primary OS = **Linux** (kiosk + GPU + camera +
  serial reliability, reuses systemd units); **Windows Inno Setup `.exe`** is a documented fallback
  if the box must run Windows. A literal single end-user exe is *not* a goal — the appliance is.
  See ROADMAP **Deploy track (40–44)**.
- **Why not "everything in one exe"**: Postgres and the NVIDIA driver/CUDA runtime are host-level
  and can't ship inside an app bundle; on Windows, Docker + webcam + serial + GPU together is
  fragile → the guardpost box installs **natively**, not via Docker (Docker stays a dev-DB convenience).

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
  *(Realized in Step 30: `backend/perception.py` owns the loop; camera opening is centralized in
  `face.open_capture()`; when `PERCEPTION_ENABLED=true`, `/tap` no longer opens the camera and
  logs card-only `unverified` — the camera-dead degraded mode below — until the matcher, Step 31.)*
- **Single backend worker (or shared state).** The tap buffer + events bus **+ the runtime settings
  cache and the single cached model instance** live in process memory. Running uvicorn with
  `--workers >1` splits taps/face-events across processes (correlation **fails invisibly**) and would
  also give each worker its own settings/model (hot-reload would only touch one). Decision: **pin one
  worker**; if horizontal scale is ever needed, externalize buffer/bus + settings to Redis. Document
  `--workers 1` in the systemd unit / compose.
- **Config precedence (Tuning track, Steps 50–54)**: `DB settings override > env default (.env) >
  code default`. Only the **tunable perf/device/resolution** set (device, camera res, `FACE_DET_SIZE`,
  `MIN_FACE_PX`, probe/frame-skip, `ASSOC_WINDOW_SEC`) is DB-overridable and admin-toggleable **live**
  (hot-reload). Infra/secrets (DB DSN, SMTP creds, `OPERATOR_TOKEN`) stay **env-only**. `.env.example`
  still documents defaults; the DB just overrides the tunable subset at runtime.
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
*(Realized in Step 31, `backend/matcher.py`: the tap/face rows below map to matcher
statuses `no_face` / `mismatch` / `tailgating` / `spoof`; duplicate/held-card debounce
is `TAP_COOLDOWN_SEC`; recognition-backpressure bound is `MAX_FACE_BUFFER` drop-oldest.)*
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

### 5a. Adaptive / late-bind resolution (planned refinement — NOT yet built)
**Status: stub/design only.** Current matcher resolves *every* tap on a fixed timer — it always
waits the full `ASSOC_WINDOW_SEC` before writing a verdict, even when the answer is already obvious.
Adaptive/late-bind = **resolve as soon as the outcome is certain, keep full patience only when it
isn't.**

Goal: capture the strengths, cut the cons to the floor.

- **Strength 1 — low latency for the common case.** Face-then-tap (student already in frame when
  they tap) is the norm at a kiosk. If a strong, unambiguous face is already buffered when the tap
  lands, emit `accepted` immediately instead of waiting out the window. Green light feels instant.
- **Strength 2 — no loss of patience when needed.** Tap-first / no-face-yet keeps the existing
  behavior: hold the tap, keep watching, bind if a qualifying face arrives, else `no_face` at window
  close. Adaptive never resolves *earlier* than "certain" — it only skips *needless* waiting.
- **Con to minimize — early-bind picks the wrong face in a crowd.** Committing one tap early forfeits
  the global optimality of the batched Hungarian assignment (a later tap+face pair might have been a
  better global fit). This is the whole risk; drive it to ~zero with **guards, not hope**:
  1. **Unambiguous-only early-bind.** Early-commit *only* when the best face clears
     `MATCH_THRESHOLD` **and** beats the second-best candidate by a margin `EARLY_BIND_MARGIN`
     (top1−top2 on cosine). Any ambiguity → fall back to the timed batch resolve. (Reuses the
     §5 overlap-bleed margin idea.)
  2. **Singleton context.** Only early-bind when there is exactly one qualifying face **and** no
     other pending tap whose window overlaps this face — i.e. no competition to steal optimality from.
  3. **Cooldown/debounce unchanged.** `TAP_COOLDOWN_SEC` still guards held/duplicate cards, so a fast
     early path can't double-emit.
  4. **Faces stay claimable until bound.** An early-bound face is `consumed` atomically (same flag the
     batch path uses), so it can't also become a tailgater.
- **Net effect.** Best case: instant verdict. Ambiguous/crowded case: identical to today's optimal
  batch. There is no regime where adaptive is *worse* than the current fixed-timer matcher — it is a
  strict latency win gated behind a certainty test. Tunables (proposed): `EARLY_BIND_MARGIN`
  (default conservative, e.g. 0.10 cosine), reuse `MATCH_THRESHOLD`; a global `ADAPTIVE_BIND` off-switch
  (default off until validated live) so it can ship dark and be A/B'd against the timed path.
- **Build note.** Lives entirely in `matcher.py` (`add_tap` gains a "try early-bind" check;
  `resolve` unchanged as the fallback). No perception/main/API change. Verify with the existing
  decoupled unit-test harness (inject clock + faces): assert early-bind fires only past the margin,
  and that a crowded burst yields the *same* assignment as the timed path.

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
1. **Guardpost box OS**: **Linux appliance recommended** (reliability); Windows `.exe` only if the
   institution/box mandates it. This is the one external constraint that flips the Deploy track.
2. Reader strategy: higher baud on one reader **vs** multiple readers + `door_id`? (blocks real burst throughput)
3. Attendance unit: per-tap log vs per-student-per-day roll-up?
4. Accuracy target (FAR/FRR operating point) for this population?
5. Consent/legal jurisdiction + is the school use "commercial" for the model license?
6. Camera-dead degraded mode: log as `unverified` (recommended) vs block taps entirely?
