import os
from contextlib import contextmanager
from datetime import time

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

# The default DSN is for the LOCAL DEV container only (see README / docker run). It is
# NOT a production credential — set DB_DSN in .env with a real password before deploying.
DB_DSN = os.environ.get(
    "DB_DSN", "dbname=attendance user=attendance password=attendance host=localhost port=5433"
)
# Step 21: HH:MM cutoff for "late" (default 08:00). Set empty to disable.
_LATE_CUTOFF_STR = os.environ.get("LATE_CUTOFF", "08:00")
LATE_CUTOFF = None
if _LATE_CUTOFF_STR:
    try:
        LATE_CUTOFF = time.fromisoformat(_LATE_CUTOFF_STR)
    except ValueError:
        pass


@contextmanager
def get_conn():
    conn = psycopg2.connect(DB_DSN)
    # Enable vector <-> numpy adaptation. Best-effort: the very first connection
    # (from init_db, before CREATE EXTENSION runs) has no `vector` type yet, so
    # skip silently — every later connection registers fine.
    try:
        register_vector(conn)
    except Exception:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        schema = f.read()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)


# --- Phase 1: Student CRUD ---


def insert_student(student_id: str, uid: str, name: str | None = None,
                   guardian_email: str | None = None):
    """Create a new student. Raises ValueError on duplicate student_id or uid."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO students (student_id, uid, name, guardian_email)
                    VALUES (%s, %s, %s, %s)
                    RETURNING student_id, uid, name, guardian_email
                    """,
                    (student_id, uid, name, guardian_email),
                )
                return cur.fetchone()
            except psycopg2.errors.UniqueViolation as e:
                raise ValueError(f"duplicate student_id or uid: {e}")


def update_student(student_id: str, uid: str | None = None, name: str | None = None,
                   guardian_email: str | None = None):
    """Update student fields (only non-None values). Raises ValueError if not found."""
    sets, params = [], []
    if uid is not None:
        sets.append("uid = %s")
        params.append(uid)
    if name is not None:
        sets.append("name = %s")
        params.append(name)
    if guardian_email is not None:
        sets.append("guardian_email = %s")
        params.append(guardian_email)
    if not sets:
        return get_student(student_id)
    params.append(student_id)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE students SET {", ".join(sets)}
                WHERE student_id = %s
                RETURNING student_id, uid, name, guardian_email
                """,
                params,
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"no student with student_id={student_id}")
            return row


# --- Phase 3: Review queue ---


def insert_review(log_id: int, student_id: str | None, status: str, reason: str | None = None):
    """Add a flagged tap to the review queue. Best-effort (upsert by log_id)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO review_queue (log_id, student_id, status, reason)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (log_id, student_id, status, reason),
            )
            return cur.fetchone()


def get_review_queue(limit: int = 100):
    """Unresolved review items, newest first, joined to log data."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.id, r.log_id, r.student_id, s.name AS student_name,
                       r.status, r.reason, r.created_at,
                       l.uid, l.ts AS log_ts, l.method, l.face_score,
                       l.face_match, l.liveness_score, l.liveness_pass
                FROM review_queue r
                LEFT JOIN students s ON s.student_id = r.student_id
                LEFT JOIN attendance_logs l ON l.id = r.log_id
                WHERE r.resolved_at IS NULL
                ORDER BY r.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()


def resolve_review(review_id: int, resolution: str, resolved_by: str = "operator"):
    """Resolve a review item. resolution is 'confirmed', 'override', or 'dismiss'."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE review_queue
                SET resolved_at = now(), resolved_by = %s, resolution = %s
                WHERE id = %s AND resolved_at IS NULL
                RETURNING id, log_id, student_id, status, resolved_at, resolved_by, resolution
                """,
                (resolved_by, resolution, review_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"review {review_id} not found or already resolved")
            return row


# --- Phase 5: Runtime settings ---


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value),
            )


def get_all_settings() -> dict[str, str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM settings ORDER BY key")
            return dict(cur.fetchall())


def find_student_by_uid(uid: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM students WHERE uid = %s", (uid,))
            return cur.fetchone()


def insert_log(
    uid: str,
    student_id: str | None,
    method: str,
    liveness_score: float | None = None,
    face_score: float | None = None,
    face_match: bool | None = None,
    liveness_pass: bool | None = None,
    status: str | None = None,
):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO attendance_logs
                    (uid, student_id, method, liveness_score, face_score,
                     face_match, liveness_pass, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, uid, student_id, ts, method,
                          liveness_score, face_score, face_match, liveness_pass, status
                """,
                (uid, student_id, method, liveness_score, face_score,
                 face_match, liveness_pass, status),
            )
            return cur.fetchone()


def get_student(student_id: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
            return cur.fetchone()


def set_face_embedding(student_id: str, embedding, embed_model: str | None = None):
    """Store a student's averaged reference embedding + provenance (Step 33:
    embed_model, enrolled_at). Raises if no such student."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE students
                   SET face_embedding = %s, embed_model = %s, enrolled_at = now()
                 WHERE student_id = %s
                """,
                (embedding, embed_model, student_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"no student with student_id={student_id}")


# --- Privacy / compliance (Step 20) ---


def set_consent(student_id: str, granted: bool):
    """Record biometric-consent for a student. Raises if no such student."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE students
                   SET face_consent = %s,
                       face_consent_at = CASE WHEN %s THEN now() ELSE NULL END
                 WHERE student_id = %s
                """,
                (granted, granted, student_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"no student with student_id={student_id}")


def insert_audit(actor: str, action: str, target: str | None = None, detail: str | None = None):
    """Append an operator audit entry (Step 20). Best-effort — callers wrap it so an
    audit failure never blocks the underlying action."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO audit_log (actor, action, target, detail)
                VALUES (%s, %s, %s, %s)
                RETURNING id, ts, actor, action, target, detail
                """,
                (actor, action, target, detail),
            )
            return cur.fetchone()


def get_audit(limit: int = 100):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, ts, actor, action, target, detail FROM audit_log ORDER BY ts DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()


def delete_student(student_id: str):
    """Right-to-erasure (Step 20): drop the student's attendance logs and roster row
    (which erases the embedding). Returns {logs, students} counts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE student_id = %s", (student_id,))
            log_count = cur.rowcount
            cur.execute("DELETE FROM students WHERE student_id = %s", (student_id,))
            student_count = cur.rowcount
    return {"logs": log_count, "students": student_count}


def purge_old_logs(cutoff):
    """Delete attendance logs with ts < cutoff (a datetime). Never touches roster.
    Returns rows deleted."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE ts < %s", (cutoff,))
            return cur.rowcount


def null_old_scores(cutoff):
    """Null the raw biometric scores on logs older than cutoff, keeping the row +
    status for attendance counts (Step 20 score retention). Returns rows updated."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE attendance_logs
                   SET face_score = NULL, liveness_score = NULL,
                       face_match = NULL, liveness_pass = NULL
                 WHERE ts < %s
                   AND (face_score IS NOT NULL OR liveness_score IS NOT NULL
                        OR face_match IS NOT NULL OR liveness_pass IS NOT NULL)
                """,
                (cutoff,),
            )
            return cur.rowcount


# --- Read queries for the operator API (Step 11) ---


def get_attendance(date=None, status=None, student_id=None, limit=100):
    """Attendance logs (newest first) joined to the student name. Never returns
    embeddings. All filters optional; `limit` is clamped by the caller."""
    clauses, params = [], []
    if date:
        clauses.append("l.ts::date = %s")
        params.append(date)
    if status:
        clauses.append("l.status = %s")
        params.append(status)
    if student_id:
        clauses.append("l.student_id = %s")
        params.append(student_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT l.id, l.uid, l.student_id, s.name AS student_name, l.ts,
                       l.method, l.status, l.face_score, l.face_match,
                       l.liveness_score, l.liveness_pass
                FROM attendance_logs l
                LEFT JOIN students s ON s.student_id = l.student_id
                {where}
                ORDER BY l.ts DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()


def get_students():
    """Roster with an `enrolled` flag. Deliberately omits face_embedding (PII)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT student_id, uid, name, guardian_email,
                       (face_embedding IS NOT NULL) AS enrolled,
                       face_consent, face_consent_at, embed_model, enrolled_at
                FROM students
                ORDER BY student_id
                """
            )
            return cur.fetchall()


def search_face(embedding, k: int = 1):
    """Cardless 1:N nearest-face search (Step 31 tailgater ID). Returns the k nearest
    enrolled students by cosine similarity (`1 - (emb <=> ref)`), most-similar first.
    `embedding` is a numpy float32 512-vector (register_vector adapts it)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT student_id, name, uid,
                       1 - (face_embedding <=> %s) AS similarity
                FROM students
                WHERE face_embedding IS NOT NULL
                ORDER BY face_embedding <=> %s
                LIMIT %s
                """,
                (embedding, embedding, k),
            )
            return cur.fetchall()


def find_duplicate(embedding, threshold, exclude_student_id=None, k: int = 3):
    """Duplicate-enrollment check (Step 33): 1:N vs the gallery. Returns the nearest
    OTHER enrolled student whose similarity >= threshold, or None."""
    for r in search_face(embedding, k):
        if exclude_student_id and r["student_id"] == exclude_student_id:
            continue
        if r["similarity"] is not None and r["similarity"] >= threshold:
            return r
    return None


def stale_enrollments(cutoff=None, current_model=None):
    """Re-enrollment reminders (Step 33): enrolled students whose reference is older
    than `cutoff` (a datetime) OR was made by a different model than `current_model`.
    Returns [] if neither criterion is given."""
    ors, params = [], []
    if cutoff is not None:
        ors.append("(enrolled_at IS NULL OR enrolled_at < %s)")
        params.append(cutoff)
    if current_model is not None:
        ors.append("(embed_model IS NULL OR embed_model <> %s)")
        params.append(current_model)
    if not ors:
        return []
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT student_id, name, embed_model, enrolled_at
                FROM students
                WHERE face_embedding IS NOT NULL AND ({" OR ".join(ors)})
                ORDER BY enrolled_at NULLS FIRST
                """,
                params,
            )
            return cur.fetchall()


def get_stats_today():
    """Today's tap counts keyed by status (accepted/flagged/rejected/…)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(status, 'unknown') AS status, COUNT(*)
                FROM attendance_logs
                WHERE ts::date = CURRENT_DATE
                GROUP BY status
                """
            )
            counts = {row[0]: row[1] for row in cur.fetchall()}
    return {"date": "today", "total": sum(counts.values()), "by_status": counts}


# --- Step 21: Attendance sessions, summary, CSV ---


def get_sessions(student_id: str | None = None, date: str | None = None):
    """Query the attendance_sessions view. Returns newest first."""
    clauses, params = [], []
    if student_id:
        clauses.append("s.student_id = %s")
        params.append(student_id)
    if date:
        clauses.append("s.session_date = %s")
        params.append(date)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT s.student_id, st.name AS student_name, s.session_date,
                       s.check_in, s.check_out, s.duration_minutes
                FROM attendance_sessions s
                LEFT JOIN students st ON st.student_id = s.student_id
                {where}
                ORDER BY s.check_in DESC
                """,
                params if params else None,
            )
            return cur.fetchall()


def get_summary(date: str | None = None):
    """Today's attendance summary: expected vs present/absent/late.
    `expected` = all students with a UID (roster members).
    `present`  = students who had >=1 tap (any non-unregistered status).
    `absent`   = expected students with no tap on that date.
    `late`     = present students whose first check-in >= LATE_CUTOFF.
    """
    from datetime import date as date_type

    if date:
        target_date = date_type.fromisoformat(date)
    else:
        target_date = date_type.today()
    target_str = target_date.isoformat()

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT student_id, name FROM students ORDER BY student_id")
        all_students = {r["student_id"]: r["name"] for r in cur.fetchall()}

        cur.execute(
            """
            SELECT DISTINCT student_id
            FROM attendance_logs
            WHERE ts::date = %s
              AND (status IS NULL OR status <> 'unregistered')
            """,
            (target_str,),
        )
        present_ids = {r["student_id"] for r in cur.fetchall() if r["student_id"]}

        cur.execute(
            """
            SELECT DISTINCT student_id
            FROM attendance_logs
            WHERE ts::date = %s
              AND status = 'unregistered'
            """,
            (target_str,),
        )
        unreg_ids = {r["student_id"] for r in cur.fetchall() if r["student_id"]}

    present_list = []
    late_count = 0
    for sid in sorted(present_ids):
        name = all_students.get(sid, sid)
        late = _is_late(sid, target_str)
        if late:
            late_count += 1
        present_list.append({"student_id": sid, "name": name, "late": late})

    absent_list = []
    for sid in sorted(all_students):
        if sid not in present_ids:
            absent_list.append({"student_id": sid, "name": all_students[sid]})

    return {
        "date": target_str,
        "expected": len(all_students),
        "present": present_list,
        "absent": absent_list,
        "late_count": late_count,
        "late_cutoff": LATE_CUTOFF.isoformat() if LATE_CUTOFF else None,
    }


def _is_late(student_id: str, date_str: str) -> bool:
    """Check whether a student's first tap on date_str was after LATE_CUTOFF."""
    if LATE_CUTOFF is None:
        return False
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ts::time AS t
                FROM attendance_logs
                WHERE student_id = %s
                  AND ts::date = %s
                  AND (status IS NULL OR status <> 'unregistered')
                ORDER BY ts
                LIMIT 1
                """,
                (student_id, date_str),
            )
            row = cur.fetchone()
            if row is None:
                return False
            return row[0] >= LATE_CUTOFF


def get_attendance_csv(date: str | None = None, status: str | None = None,
                       student_id: str | None = None, limit: int = 5000):
    """Same filters as get_attendance but returns raw rows for CSV export
    (no embedding columns)."""
    clauses, params = [], []
    if date:
        clauses.append("l.ts::date = %s")
        params.append(date)
    if status:
        clauses.append("l.status = %s")
        params.append(status)
    if student_id:
        clauses.append("l.student_id = %s")
        params.append(student_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT l.id, l.uid, l.student_id, s.name AS student_name,
                       l.ts, l.method, l.status,
                       l.face_score, l.face_match, l.liveness_score, l.liveness_pass
                FROM attendance_logs l
                LEFT JOIN students s ON s.student_id = l.student_id
                {where}
                ORDER BY l.ts DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()
