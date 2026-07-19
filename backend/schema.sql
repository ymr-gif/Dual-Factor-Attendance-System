CREATE TABLE IF NOT EXISTS students (
    student_id      TEXT PRIMARY KEY,
    uid             TEXT UNIQUE NOT NULL,
    name            TEXT,
    guardian_email  TEXT
);

CREATE TABLE IF NOT EXISTS attendance_logs (
    id              SERIAL PRIMARY KEY,
    uid             TEXT NOT NULL,
    student_id      TEXT REFERENCES students(student_id),
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    method          TEXT NOT NULL,
    liveness_score  REAL
);

-- Step 6 (face match 1:1). Idempotent — init_db() re-runs this file every
-- startup, so these self-migrate the existing volume on next backend restart.
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE students        ADD COLUMN IF NOT EXISTS face_embedding vector(512);
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS face_score REAL;
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS face_match BOOLEAN;

-- Step 7 (passive liveness). liveness_score already exists in the base table;
-- add the pass/fail verdict. Idempotent, self-migrates on restart.
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS liveness_pass BOOLEAN;

-- Step 9 (2FA enforcement / buddy-punch). Overall verdict per tap:
-- accepted / flagged / rejected / unverified / unregistered (see backend/decision.py).
ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS status TEXT;

-- ===== Phase B schema pass (land additive columns together; all idempotent) =====

-- Step 33 (identity/matching): embedding provenance for re-enroll reminders + model
-- migration (which model produced the stored reference, and when it was enrolled).
ALTER TABLE students ADD COLUMN IF NOT EXISTS embed_model TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS enrolled_at  TIMESTAMPTZ;

-- Step 20 (privacy/consent): consent gate for minors' biometrics. face_consent
-- defaults FALSE so existing rows are un-consented; the *policy* switch
-- FACE_CONSENT_REQUIRED (env) decides whether gating is enforced.
ALTER TABLE students ADD COLUMN IF NOT EXISTS face_consent    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS face_consent_at TIMESTAMPTZ;

-- Step 33: pgvector ANN index for cardless 1:N search (tailgater ID + manual
-- lookup). HNSW with cosine ops; idempotent. Small galleries are fine either way,
-- but this keeps 1:N sub-linear as the roster grows.
CREATE INDEX IF NOT EXISTS students_face_embedding_hnsw
    ON students USING hnsw (face_embedding vector_cosine_ops);

-- Step 20 (audit): every enroll / delete / roster edit / consent change.
CREATE TABLE IF NOT EXISTS audit_log (
    id      SERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT,
    action  TEXT NOT NULL,
    target  TEXT,
    detail  TEXT
);

-- Step 34 (review queue): schema landed early in the Phase B pass; populated later.
CREATE TABLE IF NOT EXISTS review_queue (
    id          SERIAL PRIMARY KEY,
    log_id      INTEGER REFERENCES attendance_logs(id) ON DELETE CASCADE,
    student_id  TEXT    REFERENCES students(student_id) ON DELETE SET NULL,
    status      TEXT NOT NULL,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution  TEXT
);

-- Step 50 (runtime settings): key/value store overrides env defaults at runtime.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Step 21 (attendance sessions): pairs consecutive taps by a student within a day
-- into check-in/check-out sessions. Odd-numbered taps = check-in, even = check-out.
-- A lone odd tap with no partner (still present) has check_out = NULL.
-- Excludes unregistered taps (unknown cards, no student association).
CREATE OR REPLACE VIEW attendance_sessions AS
WITH ordered AS (
    SELECT student_id, ts::date AS session_date, ts, status,
        ROW_NUMBER() OVER (PARTITION BY student_id, ts::date ORDER BY ts) AS rn
    FROM attendance_logs
    WHERE student_id IS NOT NULL
      AND (status IS NULL OR status <> 'unregistered')
),
paired AS (
    SELECT *, (rn + 1) / 2 AS pair_group
    FROM ordered
)
SELECT
    student_id,
    session_date,
    MIN(ts) AS check_in,
    CASE WHEN COUNT(*) = 2 THEN MAX(ts) ELSE NULL END AS check_out,
    CASE
        WHEN COUNT(*) = 2
        THEN ROUND(EXTRACT(EPOCH FROM (MAX(ts) - MIN(ts))) / 60)
        ELSE NULL
    END AS duration_minutes
FROM paired
GROUP BY student_id, session_date, pair_group
ORDER BY student_id, session_date, check_in;
