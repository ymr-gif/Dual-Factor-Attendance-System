"""Guardian attendance digest (Step 21).

Sends a batched daily summary email to each guardian whose child had attendance
activity on the target date. Reuses backend/notify.py's SMTP path for delivery.

Usage:
    python -m backend.digest                        # yesterday
    python -m backend.digest --date 2026-07-19      # specific date
    python -m backend.digest --dry-run              # print only, no email

Schedule via cron:
    0 18 * * * cd /home/scylla/dev/python-projects/nfc-scan && \
        /home/scylla/.pyenv/versions/3.11.8/bin/python -m backend.digest
"""

import argparse
import os
from datetime import date, timedelta

from . import db
from .notify import _build_email, _send, EMAIL_ENABLED, SMTP_HOST


def _digest_body(student_name: str, student_id: str, sessions: list[dict],
                 summary: dict) -> str:
    day = sessions[0]["session_date"] if sessions else summary.get("date", "today")
    lines = [
        f"Attendance summary for {student_name} on {day}",
        "",
    ]
    if not sessions:
        lines.append("  No attendance recorded for this date.")
        return "\n".join(lines)

    for s in sessions:
        ci = s["check_in"]
        co = s.get("check_out")
        dur = s.get("duration_minutes")
        ci_str = ci.strftime("%H:%M") if ci else "—"
        co_str = co.strftime("%H:%M") if co else "Still present"
        dur_str = f"{int(dur)} min" if dur is not None else "—"
        lines.append(f"  Check-in:  {ci_str}")
        lines.append(f"  Check-out: {co_str}")
        lines.append(f"  Duration:  {dur_str}")
        lines.append("")

    # Late flag
    for p in summary.get("present", []):
        if p["student_id"] == student_id and p.get("late"):
            lines.append("  ⚠ LATE (after cutoff)")
            lines.append("")

    lines.append("— nfc-scan attendance system")
    return "\n".join(lines)


def _digest_for_student(student: dict, target_date_str: str, summary: dict) -> str | None:
    """Build a digest email body for one student. Returns None if there's nothing
    to report (no sessions on that date)."""
    sessions = db.get_sessions(student_id=student["student_id"], date=target_date_str)
    if not sessions:
        return None
    return _digest_body(
        student_name=student["name"] or student["student_id"],
        student_id=student["student_id"],
        sessions=sessions,
        summary=summary,
    )


def run(target_date: date | None = None, dry_run: bool = False):
    target = target_date or (date.today() - timedelta(days=1))
    target_str = target.isoformat()

    summary = db.get_summary(target_str)
    all_students = db.get_students()

    sent = 0
    skipped_no_email = 0
    skipped_no_activity = 0

    for s in all_students:
        body = _digest_for_student(s, target_str, summary)
        if body is None:
            skipped_no_activity += 1
            continue
        if not EMAIL_ENABLED or not SMTP_HOST:
            print(f"[digest] WOULD email {s.get('name', s['student_id'])} "
                  f"at {s.get('guardian_email') or 'no-address'} "
                  f"(dry-run={dry_run}, email-enabled={EMAIL_ENABLED})")
            print(body)
            print("---")
            sent += 1
            continue

        guardian = s.get("guardian_email")
        if not guardian:
            skipped_no_email += 1
            print(f"[digest] no guardian email for {s['student_id']} — skip")
            continue

        student_name = s["name"] or s["student_id"]
        msg = _build_email(
            {"name": student_name, "guardian_email": guardian,
             "student_id": s["student_id"]},
            {"ts": target_str, "method": "digest", "status": ""},
            [],
        )
        msg.set_content(body)
        msg.replace_header("Subject", f"Attendance Summary for {student_name} on {target_str}")
        msg["To"] = guardian

        if dry_run:
            print(f"[digest] DRY-RUN: would send to {guardian}")
            print(body)
            print("---")
            sent += 1
        else:
            try:
                _send(msg)
                sent += 1
                print(f"[digest] sent to {guardian} ({student_name})")
            except Exception as e:
                print(f"[digest] FAILED to send to {guardian}: {e}")

    print(f"\n[digest] done: {sent} sent, {skipped_no_activity} no activity, "
          f"{skipped_no_email} no guardian email")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Guardian attendance digest")
    p.add_argument("--date", type=str, help="YYYY-MM-DD (default: yesterday)")
    p.add_argument("--dry-run", action="store_true", help="print only, no email")
    args = p.parse_args()

    d = date.fromisoformat(args.date) if args.date else None
    run(target_date=d, dry_run=args.dry_run)
