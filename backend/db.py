import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

DB_DSN = os.environ.get(
    "DB_DSN", "dbname=attendance user=attendance password=attendance host=localhost port=5433"
)


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


def set_face_embedding(student_id: str, embedding):
    """Store a student's averaged reference embedding. Raises if no such student."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE students SET face_embedding = %s WHERE student_id = %s",
                (embedding, student_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"no student with student_id={student_id}")
