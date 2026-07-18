"""Guardian notification (Steps 4 / 8).

Always prints an operator console line (the original stub behavior). When SMTP is
configured (NOTIFY_EMAIL_ENABLED=true + SMTP_HOST set), also emails the student's
guardian. Fail-open: an SMTP error is logged and swallowed — attendance still
stands, the tap never fails because email was down.

Env:
  NOTIFY_EMAIL_ENABLED  send real email (default false -> console only)
  SMTP_HOST             mail server host (required to send)
  SMTP_PORT             465 -> implicit SSL, else STARTTLS (default 587)
  SMTP_USER/SMTP_PASSWORD  login (omit for an open relay / debug server)
  SMTP_FROM             From: address (default SMTP_USER)
  SMTP_STARTTLS         use STARTTLS on non-465 ports (default true)
  SMTP_TIMEOUT          socket timeout seconds (default 10)
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "") or SMTP_USER
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes", "on")
SMTP_TIMEOUT = float(os.environ.get("SMTP_TIMEOUT", "10"))
EMAIL_ENABLED = os.environ.get("NOTIFY_EMAIL_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _flags(student: dict | None, log: dict) -> list[str]:
    """Human-readable warnings for factors that failed or couldn't verify."""
    notes = []
    face_match = log.get("face_match")
    if face_match is False:
        notes.append(f"FACE MISMATCH (score={log.get('face_score')})")
    elif face_match is None and student is not None and student.get("face_embedding") is not None:
        notes.append("face unverified (no usable probe)")

    if log.get("liveness_pass") is False:
        notes.append(f"SPOOF SUSPECTED (score={log.get('liveness_score')})")
    return notes


def _console(student: dict | None, log: dict, notes: list[str]) -> None:
    who = student["name"] if student else f"unregistered uid={log['uid']}"
    line = f"[NOTIFY] {who} tapped at {log['ts']} via {log['method']}"
    status = log.get("status")
    if status:
        line += f"  [{status.upper()}]"
    for n in notes:
        line += f"  ⚠ {n}"
    print(line)


def _build_email(student: dict, log: dict, notes: list[str]) -> EmailMessage:
    name = student["name"] or student.get("student_id") or "student"
    status = (log.get("status") or "").upper()
    rejected = log.get("status") == "rejected"

    msg = EmailMessage()
    msg["Subject"] = f"Attendance {status or 'LOGGED'}: {name}"
    msg["From"] = SMTP_FROM
    msg["To"] = student["guardian_email"]

    body = [
        ("Attendance was DENIED (2-factor check failed)." if rejected
         else f"{name} was checked in."),
        "",
        f"Student : {name} ({student.get('student_id')})",
        f"Time    : {log['ts']}",
        f"Method  : {log['method']}",
        f"Status  : {status or 'LOGGED'}",
    ]
    if notes:
        body.append("")
        body.append("Verification warnings:")
        body.extend(f"  - {n}" for n in notes)
    msg.set_content("\n".join(body))
    return msg


def _send(msg: EmailMessage) -> None:
    """Send via SSL (465) or STARTTLS (others). Login only if SMTP_USER is set."""
    ctx = ssl.create_default_context()
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=ctx) as s:
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as s:
            if SMTP_STARTTLS:
                s.starttls(context=ctx)
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)


def _email(student: dict | None, log: dict, notes: list[str]) -> None:
    if not EMAIL_ENABLED:
        return
    if student is None or not student.get("guardian_email"):
        return  # nobody to notify (unregistered card, or no guardian on file)
    if not SMTP_HOST:
        print("[notify] NOTIFY_EMAIL_ENABLED but SMTP_HOST unset — skipping email")
        return
    _send(_build_email(student, log, notes))


def notify(student: dict | None, log: dict) -> None:
    notes = _flags(student, log)
    _console(student, log, notes)
    try:
        _email(student, log, notes)
    except Exception as e:  # fail-open: email trouble never breaks a tap
        print(f"[notify] email send failed, continuing: {e}")
