"""Guardian notification (Steps 4 / 8).

Always prints an operator console line (the original stub behavior). When SMTP is
configured (NOTIFY_EMAIL_ENABLED=true + SMTP_HOST set), also emails the student's
guardian. Fail-open: an SMTP error is logged and swallowed — attendance still
stands, the tap never fails because email was down. The tap does not wait for the
send either: `notify` writes the log rows and queues the message, and the thread in
backend/sender.py sends it, with retries, inside 60 s of the entry (PC-021).

A guardian is told only about an entry that counts as attendance (PC-022), and is
told four things: the student's name, the date, the time and the entry point
(PC-023). The student ID, card UID, method, status, scores and warnings stay on the
operator console line.

Every such entry gets one `notification_log` row per channel (PC-020): DELIVERED with
the time the message was accepted, FAILED with the kind of error, or DISABLED when the
channel is off or has nobody to send to. The row is opened before the message is
queued and claimed before it is sent, so an entry is never sent twice on one channel.

Env:
  NOTIFY_EMAIL_ENABLED  send real email (default false -> console only)
  SMTP_HOST             mail server host (required to send)
  SMTP_PORT             465 -> implicit SSL, else STARTTLS (default 587)
  SMTP_USER/SMTP_PASSWORD  login (omit for an open relay / debug server)
  SMTP_FROM             From: address (default SMTP_USER)
  SMTP_STARTTLS         use STARTTLS on non-465 ports (default true)
  SMTP_TIMEOUT          socket timeout seconds (default 10); a try for an entry gets
                        less when less is left of its 60 s
  NOTIFY_SMS_ENABLED    send SMS through Semaphore (default false, PC-018)
  SEMAPHORE_API_KEY     the Semaphore account key; a secret, kept in .env only
  SEMAPHORE_TIMEOUT     seconds per SMS try (default 10), less when less is left
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
from datetime import datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

from . import db, decision, livelog, sender
from .sender import DELIVERED, FAILED, PENDING, Retryable  # noqa: F401  (statuses are read from here)

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
SEMAPHORE_API_KEY = os.environ.get("SEMAPHORE_API_KEY", "").strip()
SEMAPHORE_URL = "https://api.semaphore.co/api/v4/messages"
SEMAPHORE_TIMEOUT = float(os.environ.get("SEMAPHORE_TIMEOUT", "10"))

SMS_TEST_SKIPPED = "SMS test skipped"

# notification_log.status for a channel that sends nothing; the others are sender's
DISABLED = "DISABLED"
CHANNELS = ("email", "sms")
NO_RECIPIENT = "no recipient on file"

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


def _temporary(code) -> bool:
    return isinstance(code, int) and 400 <= code < 500


def _send(msg: EmailMessage, timeout: float | None = None) -> None:
    """Send via SSL (465) or STARTTLS (others). Login only if SMTP_USER is set.
    Returning means the server accepted the message.

    Raises `Retryable` when the message certainly did not go out and a later try may
    work: nothing was handed over yet (no connection, TLS or login trouble that is not
    a flat refusal), or the server answered the message itself with a 4xx "try later".
    Everything else is raised as it is and must not be retried: a 5xx refusal will not
    change, and after a timeout or a dropped connection during the hand-over it is not
    known whether the message left."""
    timeout = min(SMTP_TIMEOUT, timeout) if timeout else SMTP_TIMEOUT
    ctx = ssl.create_default_context()
    s = None
    try:
        try:
            if SMTP_PORT == 465:
                s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=timeout, context=ctx)
            else:
                s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=timeout)
                if SMTP_STARTTLS:
                    s.starttls(context=ctx)
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
        except smtplib.SMTPResponseException as e:
            if _temporary(e.smtp_code):
                raise Retryable(e) from e
            raise
        except Exception as e:
            raise Retryable(e) from e
        try:
            s.send_message(msg)
        except smtplib.SMTPRecipientsRefused as e:
            codes = [reply[0] for reply in e.recipients.values()]
            if codes and all(_temporary(c) for c in codes):
                raise Retryable(e) from e
            raise
        except smtplib.SMTPResponseException as e:
            if _temporary(e.smtp_code):
                raise Retryable(e) from e
            raise
    finally:
        if s is not None:
            try:
                s.quit()  # an error here must not undo a message the server accepted
            except Exception:
                s.close()


def _off_reason(channel: str, student: dict) -> str | None:
    """Why this channel sends nothing for this student, or None when it can send. The
    reason is stored on a DISABLED row; it never holds a contact."""
    if channel == "email":
        if not EMAIL_ENABLED:
            return "NOTIFY_EMAIL_ENABLED is off"
        if not SMTP_HOST:
            return "SMTP_HOST is not set"
        if not student.get("guardian_email"):
            return NO_RECIPIENT
        return None
    if not SMS_ENABLED:
        return "NOTIFY_SMS_ENABLED is off"
    if not SEMAPHORE_API_KEY:
        return "SEMAPHORE_API_KEY is not set"
    if not student.get("guardian_mobile"):
        return NO_RECIPIENT
    return None


def _send_email(student: dict, log: dict, timeout: float | None = None) -> str | None:
    """Hand the entry email to the mail server. Returning means it was accepted."""
    _send(_build_email(student, log), timeout=timeout)
    return None  # SMTP gives no message ID worth keeping


class SmsRefused(Exception):
    """Semaphore answered and did not take the message. Its text is the HTTP status
    only; the reply body can repeat the number."""

    def __init__(self, status_code, what="refused"):
        super().__init__(f"SMS {what} ({status_code})")
        self.status_code = status_code


def _never_connected(e: requests.RequestException) -> bool:
    """True when the request certainly never reached Semaphore: the connection was
    not made at all. A timeout or a drop after that may follow a message it took."""
    if isinstance(e, requests.exceptions.ConnectTimeout):
        return True
    if not isinstance(e, requests.exceptions.ConnectionError):
        return False
    reason = e.args[0] if e.args else None
    if isinstance(reason, MaxRetryError):
        reason = reason.reason
    return isinstance(reason, NewConnectionError)


def _post_sms(number: str, text: str, timeout: float | None = None) -> str | None:
    """Hand one SMS to Semaphore. Returns its message ID.

    Raises `Retryable` when Semaphore certainly did not take it and a later try may
    work: no connection, or 429 / 503 ("too many requests", "unavailable"). Anything
    else is raised as it is and is not retried: a 4xx will not change, and after a
    read timeout or another 5xx it is not known whether the message was queued. The
    key goes in the request body, never in a URL, log line or error text."""
    timeout = min(SEMAPHORE_TIMEOUT, timeout) if timeout else SEMAPHORE_TIMEOUT
    data = {"apikey": SEMAPHORE_API_KEY, "number": number, "message": text,
            "sendername": SMS_SENDER}
    try:
        reply = requests.post(SEMAPHORE_URL, data=data, timeout=timeout)
    except requests.RequestException as e:
        if _never_connected(e):
            raise Retryable(e) from None
        raise
    if reply.status_code in (429, 503):
        raise Retryable(SmsRefused(reply.status_code))
    if reply.status_code != 200:
        raise SmsRefused(reply.status_code)
    try:
        (sent,) = reply.json()[:1]
        message_id = sent["message_id"]
        status = str(sent.get("status", "")).lower()
    except Exception:
        raise SmsRefused(reply.status_code, "reply not understood") from None
    if status in ("failed", "refunded"):
        raise SmsRefused(reply.status_code, status)
    return str(message_id)


def _send_sms(student: dict, log: dict, timeout: float | None = None) -> str | None:
    """Hand the entry SMS to Semaphore. Returning means it was accepted."""
    return _post_sms(student["guardian_mobile"], sms_text(student.get("name"), log["ts"]),
                     timeout)


_SENDERS = {"email": _send_email, "sms": _send_sms}


def _job(channel: str, student: dict, log: dict):
    """What the sender thread calls for one message: it is given the seconds it may
    take and returns the provider's message ID or None."""
    send = _SENDERS[channel]
    name = "email" if channel == "email" else "SMS"

    def job(timeout):
        # The dashboard's scan steps show what became of the message (a scan's
        # guardian step stays open until this answers).
        try:
            message_id = send(student, log, timeout)
        except Exception as e:
            retry = ", trying again" if isinstance(e, Retryable) else ""
            _step(log, f"guardian {name} not sent ({sender.error_text(e)}{retry})", not retry)
            raise
        _step(log, f"guardian {name} sent in {_since(log):.1f} s", True)
        return message_id

    return job


def _since(log: dict) -> float:
    """Seconds from the entry to now: what notification_log stores as latency."""
    ts = log.get("ts")
    if not isinstance(ts, datetime):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.astimezone()
    return (datetime.now(timezone.utc) - ts).total_seconds()


def _step(log: dict, text: str, done: bool) -> None:
    if log.get("uid"):
        livelog.stage(log["uid"], "notify", text, done=done)


def _queue(channel: str, student: dict, log: dict) -> None:
    """Record one channel for one entry (PC-020) and hand the message to the
    background sender (PC-021). Nothing is sent from here."""
    reason = _off_reason(channel, student)
    if reason:
        db.insert_notification(log["id"], channel, log["ts"], DISABLED, reason)
        return
    row = db.insert_notification(log["id"], channel, log["ts"])
    if row is None:
        return  # this entry already has its message on this channel
    sender.submit(row["id"], log["ts"], _job(channel, student, log))


def _rebuild(row: dict):
    """The send call for a message read back from the log after a restart, or None
    when it can no longer be sent."""
    student = {k: row.get(k) for k in ("name", "guardian_email", "guardian_mobile")}
    if row["channel"] not in _SENDERS or _off_reason(row["channel"], student):
        return None
    return _job(row["channel"], student, {"id": row["log_id"], "ts": row["t0"]})


def start_sender() -> None:
    """Called once when the backend starts."""
    sender.start(_rebuild)


_error_text = sender.error_text


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


SMS_CHECK = ("This number was saved as a guardian contact in the S.A.F.E. attendance "
             f"system of {SCHOOL}. No reply is needed.")


def _sms_test(mobile: str | None) -> str:
    if not mobile:
        return "no mobile on file"
    if not SMS_ENABLED:
        return SMS_TEST_SKIPPED
    if not SEMAPHORE_API_KEY:
        return f"{SMS_TEST_SKIPPED} (SEMAPHORE_API_KEY is not set)"
    try:
        _post_sms(mobile, f"{SMS_SENDER}: {SMS_CHECK}")
    except Exception as e:
        return f"SMS test failed: {_error_text(e)}"
    return "SMS test sent"


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
    for channel in CHANNELS:
        try:
            _queue(channel, student, log)
        except Exception as e:  # fail-open: notification trouble never breaks a tap
            print(f"[notify] {channel} not recorded, continuing: {_error_text(e)}")
