"""Privacy & compliance policy (Step 20).

Children's biometrics are sensitive. This module holds the *policy* — the consent
gate and the data-retention windows — while db.py holds the SQL. Everything is
env-driven and fail-open-compatible: gating skips face work, it never blocks a tap
from logging NFC-only.

  - Consent gate: FACE_CONSENT_REQUIRED. When on, enrollment and face matching
    require students.face_consent = TRUE. When off (default, for dev/back-compat),
    no gating. Flip it on in production before enrolling real children.
  - Retention: ATTENDANCE_RETENTION_DAYS deletes whole logs; SCORE_RETENTION_DAYS
    nulls just the raw biometric scores (keeps the row + status for counts). 0/unset
    = keep forever. Run via `make purge` (or a cron).
"""

import os
from datetime import datetime, timedelta, timezone

from . import db


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


FACE_CONSENT_REQUIRED = _bool("FACE_CONSENT_REQUIRED", "false")
ATTENDANCE_RETENTION_DAYS = _int("ATTENDANCE_RETENTION_DAYS", 0)  # 0 = keep forever
SCORE_RETENTION_DAYS = _int("SCORE_RETENTION_DAYS", 0)  # 0 = keep forever


def consent_ok(student) -> bool:
    """True if face work is permitted for this student. When the policy is off, always
    true (back-compat). When on, requires an explicit face_consent = TRUE."""
    if not FACE_CONSENT_REQUIRED:
        return True
    return bool(student and student.get("face_consent"))


def enroll_allowed(student) -> bool:
    """Enrollment consent gate (same policy as matching)."""
    return consent_ok(student)


def purge(now=None) -> dict:
    """Apply the retention windows. Returns counts of what changed. Never touches the
    roster. Idempotent — safe to run repeatedly (cron / `make purge`)."""
    now = now or datetime.now(timezone.utc)
    result = {"logs_deleted": 0, "scores_nulled": 0}
    if ATTENDANCE_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=ATTENDANCE_RETENTION_DAYS)
        result["logs_deleted"] = db.purge_old_logs(cutoff)
    if SCORE_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=SCORE_RETENTION_DAYS)
        result["scores_nulled"] = db.null_old_scores(cutoff)
    return result


def main():
    r = purge()
    print(
        f"purge: deleted {r['logs_deleted']} log(s) older than "
        f"{ATTENDANCE_RETENTION_DAYS}d; nulled scores on {r['scores_nulled']} log(s) older than "
        f"{SCORE_RETENTION_DAYS}d "
        f"({'no-op — retention unset' if not (ATTENDANCE_RETENTION_DAYS or SCORE_RETENTION_DAYS) else 'ok'})"
    )


if __name__ == "__main__":
    main()
