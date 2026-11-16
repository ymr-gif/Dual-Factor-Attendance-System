"""Guardian notification (Steps 4 / 8).

Always prints an operator console line (the original stub behavior). When SMTP is
configured (NOTIFY_EMAIL_ENABLED=true + SMTP_HOST set), also emails the student's
guardian. Fail-open: an SMTP error is logged and swallowed — attendance still
stands, the tap never fails because email was down.

A guardian is told only about an entry that counts as attendance (PC-022), and is
told four things: the student's name, the date, the time and the entry point
(PC-023). The student ID, card UID, method, status, scores and warnings stay on the
operator console line.

Env:
  NOTIFY_EMAIL_ENABLED  send real email (default false -> console only)
  SMTP_HOST             mail server host (required to send)
  SMTP_PORT             465 -> implicit SSL, else STARTTLS (default 587)
  SMTP_USER/SMTP_PASSWORD  login (omit for an open relay / debug server)
  SMTP_FROM             From: address (default SMTP_USER)
  SMTP_STARTTLS         use STARTTLS on non-465 ports (default true)
  SMTP_TIMEOUT          socket timeout seconds (default 10)
  NOTIFY_SMS_ENABLED    send SMS (default false; the sender is not built yet, PC-018)
  ENTRY_POINT           where the reader stands, as the message words it
                        (default "main guardpost")
  SEMAPHORE_SENDER      sender name every SMS starts with (default SAFEHSCI)
  ATTENDANCE_TZ         zone the date and time are written in (default: this machine's)

When a guardian contact is saved, `contact_test` sends one message to it so a wrong
address shows up at the roster desk and not on the first school day (PC-019).
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from . import decision

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
SMS_ENABLED = os.environ.get("NOTIFY_SMS_ENABLED", "false").lower() in ("1", "true", "yes", "on")

SMS_TEST_SKIPPED = "SMS test skipped"

SCHOOL = "Hua Siong College of Iloilo"
ENTRY_POINT = os.environ.get("ENTRY_POINT", "").strip() or "main guardpost"
# The provider requires every message to start with the approved sender name.
SMS_SENDER = os.environ.get("SEMAPHORE_SENDER", "").strip() or "SAFEHSCI"
# One SMS. Past this the provider splits the message and bills each part.
SMS_MAX_CHARS = 160
NAME_FALLBACK = "Your student"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _zone(name: str | None):
    """The tzinfo for an IANA name; None (this machine's zone) when it is unset or
    not known here."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        print(f"[notify] time zone {name!r} is not known here; using this machine's zone")
        return None


SCHOOL_ZONE = _zone(os.environ.get("ATTENDANCE_TZ"))


def when_text(ts: datetime) -> tuple[str, str]:
    """The entry's date and time on the school's clock, e.g. ("Nov 24, 2026",
    "7:12 AM"). Spelled out here, so the wording does not follow the locale."""
    if ts.tzinfo is not None:
        ts = ts.astimezone(SCHOOL_ZONE)
    day = f"{_MONTHS[ts.month - 1]} {ts.day}, {ts.year}"
    clock = f"{ts.hour % 12 or 12}:{ts.minute:02d} {'AM' if ts.hour < 12 else 'PM'}"
    return day, clock


def _name(student: dict) -> str:
    return " ".join((student.get("name") or "").split()) or NAME_FALLBACK


def entry_sentence(name: str, ts: datetime, entry_point: str | None = None) -> str:
    """The one sentence a guardian is sent, by SMS and by email."""
    day, clock = when_text(ts)
    return f"{name} entered the {SCHOOL} {entry_point or ENTRY_POINT} on {day} at {clock}."


def sms_text(name: str | None, ts: datetime, entry_point: str | None = None) -> str:
    """The entry SMS: the sender name, then the sentence. Kept to one SMS by
    shortening the name (given name and surname, then a cut with "..."); the date and
    the time are never cut."""
    def build(n):
        return f"{SMS_SENDER}: {entry_sentence(n, ts, entry_point)}"

    name = " ".join((name or "").split()) or NAME_FALLBACK
    text = build(name)
    if len(text) <= SMS_MAX_CHARS:
        return text
    words = name.split()
    if len(words) > 2:
        name = f"{words[0]} {words[-1]}"
        text = build(name)
        if len(text) <= SMS_MAX_CHARS:
            return text
    room = SMS_MAX_CHARS - len(build("")) - 3
    return build(name[: max(room, 0)].rstrip() + "...")


def guardian_is_told(student: dict | None, log: dict) -> bool:
    """PC-022: only an entry that counts as attendance, by a student on the roster,
    reaches a guardian. A denied or unknown tap is the operator's to handle."""
    status = log.get("status")
    if student is None or not status:
        return False
    return status not in decision.not_counted_statuses()


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
        line += f"  WARNING: {n}"
    print(line)


def _build_email(student: dict, log: dict) -> EmailMessage:
    """The entry email: the same four facts as the SMS and nothing else (PC-023)."""
    name = _name(student)
    msg = EmailMessage()
    msg["Subject"] = f"S.A.F.E. entry notice: {name}"
    msg["From"] = SMTP_FROM
    msg["To"] = student["guardian_email"]
    msg.set_content(
        f"{entry_sentence(name, log['ts'])}\n\n"
        "This message was sent by the S.A.F.E. attendance system. No reply is needed."
    )
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


def _email(student: dict, log: dict) -> None:
    if not EMAIL_ENABLED:
        return
    if not student.get("guardian_email"):
        return  # no guardian email on file
    if not SMTP_HOST:
        print("[notify] NOTIFY_EMAIL_ENABLED but SMTP_HOST unset — skipping email")
        return
    _send(_build_email(student, log))


def _error_text(e: Exception) -> str:
    """What may be stored or shown about a failed send: the kind of error and the SMTP
    reply code. Never the exception text, which can carry the recipient's address."""
    code = getattr(e, "smtp_code", None)
    return f"{type(e).__name__} {code}" if code else type(e).__name__


def _email_test(address: str | None) -> str:
    if not address:
        return "no email on file"
    if not EMAIL_ENABLED:
        return "email test skipped (NOTIFY_EMAIL_ENABLED is off)"
    if not SMTP_HOST:
        return "email test skipped (SMTP_HOST is not set)"
    msg = EmailMessage()
    msg["Subject"] = "S.A.F.E. attendance: contact check"
    msg["From"] = SMTP_FROM
    msg["To"] = address
    msg.set_content(
        "This address was saved as a guardian contact in the S.A.F.E. attendance "
        "system. This message only checks that it can be reached. No reply is needed."
    )
    try:
        _send(msg)
    except Exception as e:
        return f"email test failed: {_error_text(e)}"
    return "email test sent"


def _sms_test(mobile: str | None) -> str:
    if not mobile:
        return "no mobile on file"
    # NOTIFY_SMS_ENABLED=true has nothing to switch on until the sender exists (PC-018).
    return SMS_TEST_SKIPPED


def contact_test(student: dict, email: bool = True, sms: bool = True) -> dict:
    """Send one message to each guardian contact just saved (PC-019). Returns a line
    per channel for the operator and the audit log; the lines never hold the contact
    itself. Never raises: a failed test is a result, not an error."""
    result = {}
    if email:
        result["email"] = _email_test(student.get("guardian_email"))
    if sms:
        result["sms"] = _sms_test(student.get("guardian_mobile"))
    return result


def notify(student: dict | None, log: dict) -> None:
    notes = _flags(student, log)
    _console(student, log, notes)
    if not guardian_is_told(student, log):
        return
    try:
        _email(student, log)
    except Exception as e:  # fail-open: email trouble never breaks a tap
        print(f"[notify] email send failed, continuing: {_error_text(e)}")
