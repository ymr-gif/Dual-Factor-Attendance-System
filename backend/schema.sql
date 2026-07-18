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
