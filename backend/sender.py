"""Background sender for guardian messages (PC-021).

A tap writes its notification rows and hands each message to `submit`, which only
appends to a list. One thread takes the messages from there, so the answer to a tap
never waits for a mail server or an SMS provider.

Rules:
  - A message is claimed in `notification_log` before it is sent. A row that is
    already claimed or finished is left alone, so no entry is sent twice.
  - A send that certainly did not go out (`Retryable`) is tried again after 2, 4, 8
    and then every 16 seconds. Any other error ends the message as FAILED at once:
    when it is not known whether the message left, a second send could deliver it
    twice.
  - The deadline is 60 seconds after the entry (t0). A message that is not out by
    then is FAILED, and so is one whose next try would start at or after the
    deadline. Each try is given only the time that is left.
  - On start, `recover` reads the PENDING rows back. Never claimed and younger than
    the deadline: queued again. Claimed: FAILED, because the backend stopped during
    the send and the message may have left. Older: FAILED.

One thread, in this process. Messages go out one at a time, so a server that is slow
to answer holds back the ones behind it; they fail at their own deadlines. A row whose
result could not be written (the database went away mid-send) stays PENDING and
claimed until the next start, which fails it.
"""

import threading
from datetime import datetime, timedelta, timezone

from . import db

# notification_log.status, for a message that was to be sent
PENDING = "PENDING"
DELIVERED = "DELIVERED"
FAILED = "FAILED"

DEADLINE_SEC = 60
BACKOFF_SEC = (2, 4, 8, 16)
IDLE_SEC = 1.0  # how long the thread sleeps with nothing due
DB_RETRY_SEC = 2  # wait after the database could not be reached

INTERRUPTED = "interrupted during send"


def error_text(e: Exception) -> str:
    """What may be stored or shown about a failed send: the kind of error and the
    reply code. Never the exception text, which can carry the recipient's address."""
    if isinstance(e, Retryable):
        return str(e)
    code = getattr(e, "smtp_code", None) or getattr(e, "status_code", None)
    return f"{type(e).__name__} {code}" if code else type(e).__name__


class Retryable(Exception):
    """The message certainly did not go out, and the cause may pass: no connection,
    or the server said "try later". Its text is `error_text` of the cause."""

    def __init__(self, cause):
        super().__init__(error_text(cause) if isinstance(cause, Exception) else str(cause))


_lock = threading.Lock()
_wake = threading.Event()
_stop = threading.Event()
_jobs: list[dict] = []
_thread = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _late(job) -> str:
    text = f"not sent within {DEADLINE_SEC} s"
    return f"{text}; last error: {job['last']}" if job["last"] else text


def submit(notification_id: int, t0: datetime, send) -> None:
    """Queue one message whose PENDING row is `notification_id`. `send(seconds)` hands
    it to the mail server or the SMS provider within that many seconds and returns the
    provider's message ID or None. Nothing is sent from here, so the caller, a tap,
    does not wait."""
    if t0.tzinfo is None:
        t0 = t0.astimezone()
    job = {
        "id": notification_id,
        "deadline": t0 + timedelta(seconds=DEADLINE_SEC),
        "send": send,
        "due": None,
        "tries": 0,
        "last": None,
    }
    with _lock:
        _jobs.append(job)
    _wake.set()


def _attempt(job) -> bool:
    """One try at one message. True when it goes back in the queue."""
    left = (job["deadline"] - _now()).total_seconds()
    if left <= 0:
        db.finish_notification(job["id"], FAILED, error=_late(job))
        return False
    if not db.claim_notification(job["id"]):
        return False  # finished, or another attempt holds it
    try:
        message_id = job["send"](left)
    except Retryable as e:
        job["last"] = error_text(e)
        wait = BACKOFF_SEC[min(job["tries"], len(BACKOFF_SEC) - 1)]
        job["tries"] += 1
        job["due"] = _now() + timedelta(seconds=wait)
        if job["due"] >= job["deadline"]:
            db.finish_notification(job["id"], FAILED, error=_late(job))
            return False
        db.release_notification(job["id"], job["last"])
        return True
    except Exception as e:
        print(f"[notify] send failed: {error_text(e)}")
        db.finish_notification(job["id"], FAILED, error=error_text(e))
        return False
    db.finish_notification(job["id"], DELIVERED, provider_message_id=message_id)
    return False


def run_due() -> int:
    """Try every message that is due, oldest first. Returns how many were tried. The
    thread calls this in a loop; a test calls it directly."""
    now = _now()
    with _lock:
        due = [j for j in _jobs if j["due"] is None or j["due"] <= now]
        for job in due:
            _jobs.remove(job)
    for job in due:
        try:
            again = _attempt(job)
        except Exception as e:
            # The log could not be read or written. If the message was claimed, the
            # next claim is refused and the job ends there; it is never sent twice.
            print(f"[notify] sender could not use the log: {type(e).__name__}")
            job["due"] = _now() + timedelta(seconds=DB_RETRY_SEC)
            again = job["due"] < job["deadline"] + timedelta(seconds=DEADLINE_SEC)
        if again:
            with _lock:
                _jobs.append(job)
    return len(due)


def waiting() -> int:
    """How many messages are queued."""
    with _lock:
        return len(_jobs)


def recover(rebuild) -> dict:
    """Read back the messages a stopped backend left PENDING. `rebuild(row)` returns
    the `send` call for a row from `db.pending_notifications`, or None when the
    message can no longer be built (the channel is off, or the contact is gone)."""
    counts = {"queued": 0, "failed": 0}
    now = _now()
    for row in db.pending_notifications():
        if row["claimed_at"] is not None:
            reason = INTERRUPTED
        elif row["t0"] + timedelta(seconds=DEADLINE_SEC) <= now:
            reason = f"not sent within {DEADLINE_SEC} s; the backend was not running"
        else:
            send = rebuild(row)
            if send is not None:
                submit(row["id"], row["t0"], send)
                counts["queued"] += 1
                continue
            reason = "could not be rebuilt after a restart"
        db.finish_notification(row["id"], FAILED, error=reason)
        counts["failed"] += 1
    return counts


def _loop() -> None:
    while not _stop.is_set():
        _wake.clear()
        try:
            run_due()
        except Exception as e:
            print(f"[notify] sender loop error: {type(e).__name__}")
        _wake.wait(IDLE_SEC)


def start(rebuild=None) -> None:
    """Start the thread, once, when the backend starts. With `rebuild`, first take up
    what the last run left."""
    global _thread
    if rebuild is not None:
        try:
            counts = recover(rebuild)
            if counts["queued"] or counts["failed"]:
                print(f"[notify] after restart: {counts['queued']} message(s) queued "
                      f"again, {counts['failed']} marked FAILED")
        except Exception as e:
            print(f"[notify] pending messages not read back: {type(e).__name__}")
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="notify-sender", daemon=True)
        _thread.start()


def stop() -> None:
    """End the thread. What is still queued stays PENDING in the log."""
    global _thread
    _stop.set()
    _wake.set()
    thread, _thread = _thread, None
    if thread is not None:
        thread.join(timeout=5)
