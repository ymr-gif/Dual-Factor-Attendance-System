# Privacy & data handling (Step 20)

nfc-scan verifies identity with a **face embedding**, and the subjects are children.
This document states what is stored, why, and the controls for consent, retention,
and erasure. It is a feature, not an afterthought.

## What is stored

| Data | Where | Notes |
|---|---|---|
| Face **embedding** (512-d vector) | `students.face_embedding` (pgvector) | **No photograph is ever written to disk.** Enrollment frames are encoded in memory, averaged, then discarded. |
| Embedding provenance | `students.embed_model`, `students.enrolled_at` | Which model produced it, and when — for re-enrollment reminders and model migration. |
| Consent | `students.face_consent`, `students.face_consent_at` | Explicit biometric consent flag + timestamp. |
| Attendance logs | `attendance_logs` | uid, student, timestamp, method, per-tap status, and the raw face/liveness scores. |
| Operator actions | `audit_log` | actor, action (enroll/consent/erase), target, timestamp. |

A face embedding is **not invertible to a photograph**, but it is still biometric
**PII** and is treated as such. Embeddings are never sent to browser clients (the
roster and tap APIs strip them; the live boxes stream carries geometry only).

## Consent gate

`FACE_CONSENT_REQUIRED` (env, default **off** for development). When **on**:

- Enrollment refuses unless the student has `face_consent = TRUE`.
- Face matching / liveness is **skipped** for un-consented students — their taps
  still log, NFC-only, as `unverified` (never blocked).

Record consent via CLI (`python -m backend.enroll S001 --consent …`) or API
(`POST /api/students/{id}/consent {"granted": true}`). Turn the policy **on in
production before enrolling any real child.**

## Retention & purge

Two independent windows, both **0 = keep forever** by default:

- `ATTENDANCE_RETENTION_DAYS` — delete whole attendance logs older than N days.
- `SCORE_RETENTION_DAYS` — null just the raw biometric scores on older logs, keeping
  the row + status so attendance counts survive.

Apply with `make purge` (or a cron / systemd timer running `python -m backend.privacy`).
Purge **never touches the roster**.

## Right to erasure

`DELETE /api/students/{id}` drops the student's embedding (roster row) **and** their
attendance logs, and records an `erase` entry in the audit log. This is irreversible.

## Audit log

Every enroll, consent change, and erasure writes to `audit_log` (`actor`, `action`,
`target`, `ts`). Read it at `GET /api/audit`. The actor comes from the optional
`X-Operator-Actor` header (shared-token auth has no inherent user identity).

## Not yet done

- **Embedding encryption at rest** (pgcrypto or app-level) is a documented second
  pass — see ROADMAP Step 20. The key-management tradeoff (a key on the same box
  protects against disk theft, not host compromise) must be decided first.
- The legal **consent-collection workflow** with guardians is an institutional
  process, out of scope for the code; the gate above enforces its outcome.
