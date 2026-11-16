"""The background sender (PC-021): a tap never waits for a send, a message is tried
again only when it certainly did not go out, and nothing is sent after 60 s or twice.
The clock is a value the test moves; `run_due` is called by hand, except in the one
test that starts the thread.
"""

import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import pytest

from backend import db, notify, sender

T0 = datetime(2026, 11, 24, 7, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def at(self, seconds):
        self.now = T0 + timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def clock(monkeypatch, fake_db):
    fake_db.patch_notifications(monkeypatch, db)
    monkeypatch.setattr(sender, "_jobs", [])
    clock = Clock()
    monkeypatch.setattr(sender, "_now", lambda: clock.now)
    return clock


class Send:
    """A send call that plays out a list of results: an exception to raise, or a
    message ID to return. It notes when it was called and with how much time."""

    def __init__(self, clock, *results):
        self.clock, self.results = clock, list(results)
        self.at, self.given = [], []

    def __call__(self, seconds):
        self.at.append((self.clock.now - T0).total_seconds())
        self.given.append(seconds)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def no_answer():
    return sender.Retryable(ConnectionRefusedError("smtp.example.com"))


def queued(fake_db, send, log_id=1, t0=T0):
    row = fake_db.insert_notification(log_id, "email", t0)
    sender.submit(row["id"], t0, send)
    return fake_db.notifications[-1]


def run_until(clock, seconds):
    """Let the sender look at its queue once a second, as the thread does."""
    for second in range(seconds + 1):
        clock.at(second)
        sender.run_due()


# --- the tap does not wait ---


def test_queueing_a_message_sends_nothing(clock, fake_db):
    send = Send(clock, None)

    row = queued(fake_db, send)

    assert send.at == []
    assert (row["status"], row["attempts"]) == ("PENDING", 0)
    assert sender.waiting() == 1


def test_notify_writes_the_row_and_queues_the_message(clock, fake_db, monkeypatch):
    monkeypatch.setattr(notify, "EMAIL_ENABLED", True)
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify, "_send", lambda msg, timeout=None: sent.append(timeout))
    sent = []
    student = {"student_id": "S1", "name": "Juan", "guardian_email": "g@example.com"}

    notify.notify(student, {"id": 7, "uid": "04A1", "ts": T0, "method": "nfc",
                            "status": "accepted"})

    assert sent == []  # the tap is answered here
    (row,) = [n for n in fake_db.notifications if n["channel"] == "email"]
    assert row["status"] == "PENDING"

    clock.at(1)
    sender.run_due()

    assert sent == [59.0]  # what is left of the 60 s; _send caps it at SMTP_TIMEOUT
    assert row["status"] == "DELIVERED"


# --- one message ---


def test_a_message_that_goes_out_is_delivered_on_the_first_try(clock, fake_db):
    send = Send(clock, "provider-id-1")
    row = queued(fake_db, send)

    assert sender.run_due() == 1

    assert (row["status"], row["attempts"]) == ("DELIVERED", 1)
    assert row["provider_message_id"] == "provider-id-1"
    assert sender.waiting() == 0
    assert sender.run_due() == 0


def test_a_send_that_did_not_go_out_is_tried_again_after_2_then_4_seconds(clock, fake_db):
    send = Send(clock, no_answer(), no_answer(), None)
    row = queued(fake_db, send)

    sender.run_due()
    assert (row["status"], row["claimed"], row["error"]) == (
        "PENDING", False, "ConnectionRefusedError")

    run_until(clock, 10)

    assert send.at == [0, 2, 6]
    assert (row["status"], row["attempts"]) == ("DELIVERED", 3)


def test_a_server_that_never_answers_is_tried_until_the_60_seconds_are_up(clock, fake_db):
    send = Send(clock, no_answer())
    row = queued(fake_db, send)

    run_until(clock, 120)

    assert send.at == [0, 2, 6, 14, 30, 46]  # a 7th try would start at 62
    assert row["status"] == "FAILED"
    assert row["error"] == "not sent within 60 s; last error: ConnectionRefusedError"
    assert row["t1"] is None and row["latency_ms"] is None
    assert sender.waiting() == 0


def test_each_try_is_given_only_the_time_that_is_left(clock, fake_db):
    send = Send(clock, no_answer())
    queued(fake_db, send)

    run_until(clock, 120)

    assert send.given == [60, 58, 54, 46, 30, 14]


@pytest.mark.parametrize(
    "error, stored",
    [
        (TimeoutError("timed out talking to guardian@example.com"), "TimeoutError"),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"),
         "SMTPServerDisconnected"),
        (smtplib.SMTPDataError(554, b"rejected"), "SMTPDataError 554"),
    ],
)
def test_a_send_that_may_have_gone_out_or_was_refused_is_never_tried_again(
    clock, fake_db, error, stored
):
    send = Send(clock, error)
    row = queued(fake_db, send)

    run_until(clock, 120)

    assert send.at == [0]
    assert (row["status"], row["error"], row["attempts"]) == ("FAILED", stored, 1)


def test_a_message_first_reached_after_its_deadline_is_failed_unsent(clock, fake_db):
    send = Send(clock, None)
    row = queued(fake_db, send)

    clock.at(60)
    sender.run_due()

    assert send.at == []
    assert (row["status"], row["error"]) == ("FAILED", "not sent within 60 s")


def test_a_message_another_attempt_holds_is_left_alone(clock, fake_db):
    send = Send(clock, None)
    row = queued(fake_db, send)
    fake_db.claim_notification(row["id"])

    sender.run_due()

    assert send.at == []
    assert sender.waiting() == 0


def test_a_slow_message_does_not_send_the_one_behind_it_twice(clock, fake_db):
    first, second = Send(clock, no_answer(), None), Send(clock, None)
    a = queued(fake_db, first, log_id=1)
    b = queued(fake_db, second, log_id=2)

    run_until(clock, 5)

    assert (first.at, second.at) == ([0, 2], [0])
    assert (a["status"], b["status"]) == ("DELIVERED", "DELIVERED")


def test_a_database_that_cannot_be_reached_does_not_lose_or_repeat_a_message(
    clock, fake_db, monkeypatch, capsys
):
    send = Send(clock, None)
    row = queued(fake_db, send)
    claim = fake_db.claim_notification

    def down(notification_id):
        raise ConnectionError("postgres is down")

    monkeypatch.setattr(db, "claim_notification", down)
    sender.run_due()  # must not raise
    assert send.at == [] and sender.waiting() == 1

    monkeypatch.setattr(db, "claim_notification", claim)
    run_until(clock, 5)

    assert send.at == [2]
    assert row["status"] == "DELIVERED"
    assert "postgres is down" not in capsys.readouterr().out


def test_a_result_that_could_not_be_written_is_not_sent_again(clock, fake_db, monkeypatch):
    send = Send(clock, None)
    row = queued(fake_db, send)

    def down(*args, **kwargs):
        raise ConnectionError("postgres is down")

    monkeypatch.setattr(db, "finish_notification", down)
    run_until(clock, 120)

    assert send.at == [0]
    assert (row["status"], row["claimed"]) == ("PENDING", True)  # failed at next start


# --- after a restart ---


def entry(fake_db, seconds_ago, uid, clock):
    fake_db.add_student({"student_id": "S" + uid, "uid": uid, "name": "Juan Dela Cruz",
                         "guardian_email": "guardian@example.com"})
    log = fake_db.insert_log(uid, "S" + uid, "nfc", status="accepted")
    t0 = clock.now - timedelta(seconds=seconds_ago)
    fake_db.insert_notification(log["id"], "email", t0)
    return fake_db.notifications[-1]


@pytest.fixture
def email_on(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "EMAIL_ENABLED", True)
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify, "_send", lambda msg, timeout=None: sent.append(msg))
    return sent


def test_a_young_unsent_message_is_sent_after_a_restart(clock, fake_db, email_on):
    row = entry(fake_db, 20, "0401", clock)

    assert sender.recover(notify._rebuild) == {"queued": 1, "failed": 0}
    sender.run_due()

    (msg,) = email_on
    assert msg["To"] == "guardian@example.com"
    assert "Juan Dela Cruz entered" in msg.get_content()
    assert row["status"] == "DELIVERED"


def test_its_deadline_still_counts_from_the_entry(clock, fake_db, email_on):
    row = entry(fake_db, 20, "0401", clock)
    sender.recover(notify._rebuild)

    clock.at(40)  # 60 s after the entry
    sender.run_due()

    assert email_on == []
    assert row["status"] == "FAILED"


def test_a_message_that_was_being_sent_when_the_backend_stopped_is_not_sent_again(
    clock, fake_db, email_on
):
    row = entry(fake_db, 5, "0401", clock)
    fake_db.claim_notification(row["id"])

    assert sender.recover(notify._rebuild) == {"queued": 0, "failed": 1}
    sender.run_due()

    assert email_on == []
    assert (row["status"], row["error"]) == ("FAILED", "interrupted during send")


def test_a_message_older_than_60_seconds_is_failed_after_a_restart(clock, fake_db, email_on):
    row = entry(fake_db, 60, "0401", clock)

    assert sender.recover(notify._rebuild) == {"queued": 0, "failed": 1}

    assert email_on == []
    assert row["status"] == "FAILED"
    assert row["error"] == "not sent within 60 s; the backend was not running"


def test_a_message_that_can_no_longer_be_built_is_failed(clock, fake_db, email_on, monkeypatch):
    row = entry(fake_db, 5, "0401", clock)
    monkeypatch.setattr(notify, "EMAIL_ENABLED", False)

    assert sender.recover(notify._rebuild) == {"queued": 0, "failed": 1}
    assert row["status"] == "FAILED"


def test_rows_that_are_finished_are_not_read_back(clock, fake_db, email_on):
    row = entry(fake_db, 5, "0401", clock)
    fake_db.finish_notification(row["id"], "DELIVERED")

    assert sender.recover(notify._rebuild) == {"queued": 0, "failed": 0}


def test_start_survives_a_log_it_cannot_read(monkeypatch, capsys):
    def down():
        raise ConnectionError("postgres is down")

    monkeypatch.setattr(db, "pending_notifications", down)
    try:
        sender.start(notify._rebuild)  # must not raise
        assert "not read back" in capsys.readouterr().out
    finally:
        sender.stop()


# --- the thread ---


def test_the_thread_sends_what_is_queued(fake_db, monkeypatch):
    monkeypatch.setattr(sender, "_now", lambda: datetime.now(timezone.utc))
    done = threading.Event()

    def send(seconds):
        done.set()
        return "sent-by-thread"

    sender.start()
    try:
        t0 = datetime.now(timezone.utc)
        row = fake_db.insert_notification(1, "email", t0)
        sender.submit(row["id"], t0, send)
        assert done.wait(5)
    finally:
        sender.stop()

    assert fake_db.notifications[-1]["status"] == "DELIVERED"
    assert fake_db.notifications[-1]["provider_message_id"] == "sent-by-thread"


# --- which SMTP failures may be tried again ---


class FakeSMTP:
    """smtplib.SMTP with one planned failure."""

    fail_at, error, sent, timeout = None, None, [], None

    def __init__(self, host, port, timeout=None, **kwargs):
        FakeSMTP.timeout = timeout
        self._step("connect")

    def _step(self, name):
        if FakeSMTP.fail_at == name:
            raise FakeSMTP.error

    def starttls(self, context=None):
        self._step("starttls")

    def login(self, user, password):
        self._step("login")

    def send_message(self, msg):
        self._step("send")
        FakeSMTP.sent.append(msg)

    def quit(self):
        self._step("quit")

    def close(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify, "SMTP_PORT", 587)
    monkeypatch.setattr(notify, "SMTP_USER", "safe@example.com")
    monkeypatch.setattr(notify, "SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setattr(notify, "SMTP_STARTTLS", True)
    monkeypatch.setattr(notify, "SMTP_TIMEOUT", 10.0)
    monkeypatch.setattr(FakeSMTP, "fail_at", None)
    monkeypatch.setattr(FakeSMTP, "sent", [])

    def fail(at, error):
        monkeypatch.setattr(FakeSMTP, "fail_at", at)
        monkeypatch.setattr(FakeSMTP, "error", error)

    return fail


def message():
    msg = EmailMessage()
    msg["To"] = "guardian@example.com"
    msg.set_content("entry")
    return msg


@pytest.mark.parametrize(
    "at, error, stored",
    [
        ("connect", ConnectionRefusedError(), "ConnectionRefusedError"),
        ("connect", TimeoutError(), "TimeoutError"),
        ("starttls", smtplib.SMTPServerDisconnected("closed"), "SMTPServerDisconnected"),
        ("login", smtplib.SMTPAuthenticationError(454, b"try later"),
         "SMTPAuthenticationError 454"),
        ("send", smtplib.SMTPDataError(451, b"try later"), "SMTPDataError 451"),
        ("send", smtplib.SMTPSenderRefused(421, b"busy", "safe@example.com"),
         "SMTPSenderRefused 421"),
        ("send", smtplib.SMTPRecipientsRefused({"guardian@example.com": (450, b"busy")}),
         "SMTPRecipientsRefused"),
    ],
)
def test_a_send_that_did_not_go_out_may_be_tried_again(smtp, at, error, stored):
    smtp(at, error)

    with pytest.raises(sender.Retryable) as caught:
        notify._send(message())

    assert str(caught.value) == stored
    assert FakeSMTP.sent == []


@pytest.mark.parametrize(
    "at, error",
    [
        ("login", smtplib.SMTPAuthenticationError(535, b"bad password")),
        ("send", smtplib.SMTPDataError(554, b"rejected")),
        ("send", smtplib.SMTPRecipientsRefused({"guardian@example.com": (550, b"no user")})),
        ("send", TimeoutError()),  # it may have left
        ("send", smtplib.SMTPServerDisconnected("closed")),  # it may have left
    ],
)
def test_a_refusal_or_an_unknown_outcome_is_not_tried_again(smtp, at, error):
    smtp(at, error)

    with pytest.raises(type(error)) as caught:
        notify._send(message())

    assert not isinstance(caught.value, sender.Retryable)


def test_trouble_closing_the_connection_does_not_undo_a_sent_message(smtp):
    smtp("quit", TimeoutError())

    notify._send(message())  # must not raise

    assert len(FakeSMTP.sent) == 1


@pytest.mark.parametrize("left, used", [(None, 10.0), (45, 10.0), (3, 3)])
def test_a_try_never_gets_more_time_than_is_left(smtp, left, used):
    notify._send(message(), timeout=left)

    assert FakeSMTP.timeout == used
