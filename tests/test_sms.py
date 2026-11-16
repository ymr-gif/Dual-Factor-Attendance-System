"""The guardian SMS through Semaphore (PC-018). No request leaves the machine:
`requests.post` is replaced by a fake that answers as Semaphore would, or fails the
way a network does. The key is a made-up value and must never show up in a row, a
result or the console.
"""

from datetime import datetime, timezone

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

from backend import db, decision, notify, sender

ENTRY_TS = datetime(2026, 11, 23, 23, 12, tzinfo=timezone.utc)
KEY = "made-up-key-for-tests"
MOBILE = "09171234567"


class Reply:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else [
            {"message_id": 1234567, "status": "Pending", "recipient": "639171234567"}]

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Semaphore:
    """Stands in for requests.post. Plays a list of answers: a Reply, or an
    exception to raise."""

    def __init__(self, *answers):
        self.answers = list(answers) or [Reply()]
        self.calls = []

    def __call__(self, url, data=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "data": dict(data), "timeout": timeout})
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def sms_on(monkeypatch, fake_db):
    fake_db.patch_notifications(monkeypatch, db)
    monkeypatch.setattr(notify, "SMS_ENABLED", True)
    monkeypatch.setattr(notify, "SEMAPHORE_API_KEY", KEY)
    monkeypatch.setattr(notify, "SEMAPHORE_TIMEOUT", 10.0)
    monkeypatch.setattr(notify, "SMS_SENDER", "SAFEHSCI")
    monkeypatch.setattr(notify, "EMAIL_ENABLED", False)
    monkeypatch.setattr(sender, "_jobs", [])
    monkeypatch.setattr(sender, "_now", lambda: ENTRY_TS)


@pytest.fixture
def semaphore(monkeypatch):
    def install(*answers):
        fake = Semaphore(*answers)
        monkeypatch.setattr(notify.requests, "post", fake)
        return fake

    return install


def no_connection():
    reason = NewConnectionError(None, "Failed to establish a new connection")
    return requests.exceptions.ConnectionError(MaxRetryError(None, "/", reason))


def student(**over):
    row = {"student_id": "S1", "uid": "04A1", "name": "Juan Dela Cruz",
           "guardian_email": None, "guardian_mobile": MOBILE}
    row.update(over)
    return row


def entry(**over):
    row = {"id": 7, "uid": "04A1", "student_id": "S1", "ts": ENTRY_TS, "method": "nfc",
           "status": decision.ACCEPTED, "face_score": 0.8, "liveness_score": 0.9}
    row.update(over)
    return row


def sms_rows(fake_db):
    return [n for n in fake_db.notifications if n["channel"] == "sms"]


# --- the request ---


def test_the_entry_sms_is_posted_with_the_approved_text(semaphore, fake_db):
    fake = semaphore()

    notify.notify(student(), entry())
    sender.run_due()

    (call,) = fake.calls
    assert call["url"] == "https://api.semaphore.co/api/v4/messages"
    assert call["data"] == {
        "apikey": KEY,
        "number": MOBILE,
        "message": notify.sms_text("Juan Dela Cruz", ENTRY_TS),
        "sendername": "SAFEHSCI",
    }
    assert call["timeout"] == 10.0
    (row,) = sms_rows(fake_db)
    assert (row["status"], row["provider_message_id"]) == ("DELIVERED", "1234567")


def test_the_key_never_goes_in_the_url(semaphore):
    fake = semaphore()

    notify._post_sms(MOBILE, "SAFEHSCI: hello")

    assert KEY not in fake.calls[0]["url"]


def test_the_tap_does_not_wait_for_semaphore(semaphore, fake_db):
    fake = semaphore()

    notify.notify(student(), entry())

    assert fake.calls == []
    assert sms_rows(fake_db)[0]["status"] == "PENDING"


@pytest.mark.parametrize(
    "setting, value, reason",
    [
        ("SMS_ENABLED", False, "NOTIFY_SMS_ENABLED is off"),
        ("SEMAPHORE_API_KEY", "", "SEMAPHORE_API_KEY is not set"),
    ],
)
def test_nothing_is_posted_while_sms_is_off(semaphore, fake_db, monkeypatch, setting, value,
                                             reason):
    fake = semaphore()
    monkeypatch.setattr(notify, setting, value)

    notify.notify(student(), entry())
    sender.run_due()

    assert fake.calls == []
    (row,) = sms_rows(fake_db)
    assert (row["status"], row["error"]) == ("DISABLED", reason)


def test_a_student_with_no_mobile_is_logged_disabled(semaphore, fake_db):
    fake = semaphore()

    notify.notify(student(guardian_mobile=None), entry())

    assert fake.calls == []
    (row,) = sms_rows(fake_db)
    assert (row["status"], row["error"]) == ("DISABLED", notify.NO_RECIPIENT)


def test_a_tap_that_does_not_count_sends_no_sms(semaphore, fake_db):
    fake = semaphore()

    notify.notify(student(), entry(status=decision.REJECTED))
    sender.run_due()

    assert fake.calls == [] and sms_rows(fake_db) == []


# --- which failures are tried again ---


@pytest.mark.parametrize(
    "answer, stored",
    [
        (no_connection(), "ConnectionError"),
        (requests.exceptions.ConnectTimeout(), "ConnectTimeout"),
        (Reply(429, {}), "SmsRefused 429"),
        (Reply(503, {}), "SmsRefused 503"),
    ],
)
def test_a_message_semaphore_certainly_did_not_take_may_be_tried_again(semaphore, answer,
                                                                        stored):
    semaphore(answer)

    with pytest.raises(sender.Retryable) as caught:
        notify._post_sms(MOBILE, "SAFEHSCI: hello")

    assert str(caught.value) == stored


@pytest.mark.parametrize(
    "answer, stored",
    [
        (requests.exceptions.ReadTimeout(), "ReadTimeout"),  # it may have been queued
        (requests.exceptions.ConnectionError("Connection aborted"), "ConnectionError"),
        (Reply(500, {}), "SmsRefused 500"),  # it may have been queued
        (Reply(502, {}), "SmsRefused 502"),
        (Reply(401, {}), "SmsRefused 401"),  # a wrong key will not fix itself
        (Reply(422, {}), "SmsRefused 422"),
        (Reply(200, {"number": ["The number format is invalid."]}), "SmsRefused 200"),
        (Reply(200, ValueError("not JSON")), "SmsRefused 200"),
        (Reply(200, [{"message_id": 9, "status": "Failed"}]), "SmsRefused 200"),
    ],
)
def test_a_refusal_or_an_unknown_outcome_is_not_tried_again(semaphore, answer, stored):
    semaphore(answer)

    with pytest.raises(Exception) as caught:
        notify._post_sms(MOBILE, "SAFEHSCI: hello")

    assert not isinstance(caught.value, sender.Retryable)
    assert sender.error_text(caught.value) == stored


def test_a_busy_provider_is_tried_again_and_the_message_goes_out(semaphore, fake_db,
                                                                  monkeypatch):
    fake = semaphore(Reply(429, {}), Reply())
    clock = {"now": ENTRY_TS}
    monkeypatch.setattr(sender, "_now", lambda: clock["now"])

    notify.notify(student(), entry())
    sender.run_due()
    clock["now"] = ENTRY_TS.replace(second=3)
    sender.run_due()

    assert len(fake.calls) == 2
    (row,) = sms_rows(fake_db)
    assert (row["status"], row["attempts"]) == ("DELIVERED", 2)


def test_a_read_timeout_is_failed_and_not_sent_twice(semaphore, fake_db, monkeypatch):
    fake = semaphore(requests.exceptions.ReadTimeout())

    notify.notify(student(), entry())
    for _ in range(3):
        sender.run_due()

    assert len(fake.calls) == 1
    (row,) = sms_rows(fake_db)
    assert (row["status"], row["error"]) == ("FAILED", "ReadTimeout")


def test_a_try_never_gets_more_time_than_is_left(semaphore):
    fake = semaphore()

    notify._post_sms(MOBILE, "SAFEHSCI: hello", timeout=4)

    assert fake.calls[0]["timeout"] == 4


def test_the_key_and_the_number_are_never_stored_or_printed(semaphore, fake_db, capsys):
    semaphore(requests.exceptions.ReadTimeout(f"apikey={KEY}&number={MOBILE}"))

    notify.notify(student(), entry())
    sender.run_due()

    seen = str(fake_db.notifications) + capsys.readouterr().out
    assert KEY not in seen
    assert MOBILE not in seen


# --- the test message when a mobile is saved (PC-019) ---


def test_saving_a_mobile_sends_one_check_sms(semaphore):
    fake = semaphore()

    assert notify.contact_test({"guardian_mobile": MOBILE}, email=False) == {
        "sms": "SMS test sent"}

    (call,) = fake.calls
    assert call["data"]["number"] == MOBILE
    text = call["data"]["message"]
    assert text.startswith("SAFEHSCI: ")
    assert len(text) <= notify.SMS_MAX_CHARS
    assert not text.upper().startswith("TEST")


def test_a_check_sms_that_fails_says_so_without_the_number(semaphore):
    semaphore(Reply(422, {}))

    result = notify.contact_test({"guardian_mobile": MOBILE}, email=False)

    assert result == {"sms": "SMS test failed: SmsRefused 422"}


def test_no_check_sms_while_sms_is_off(semaphore, monkeypatch):
    fake = semaphore()
    monkeypatch.setattr(notify, "SMS_ENABLED", False)

    assert notify.contact_test({"guardian_mobile": MOBILE}, email=False) == {
        "sms": "SMS test skipped"}
    monkeypatch.setattr(notify, "SMS_ENABLED", True)
    monkeypatch.setattr(notify, "SEMAPHORE_API_KEY", "")
    assert notify.contact_test({"guardian_mobile": MOBILE}, email=False) == {
        "sms": "SMS test skipped (SEMAPHORE_API_KEY is not set)"}
    assert fake.calls == []


# --- after a restart ---


def test_a_pending_sms_is_rebuilt_with_the_mobile_on_file(semaphore, fake_db):
    fake = semaphore()
    row = {"id": 1, "log_id": 7, "channel": "sms", "t0": ENTRY_TS, "name": "Juan Dela Cruz",
           "guardian_email": None, "guardian_mobile": MOBILE}

    notify._rebuild(row)(5)

    assert fake.calls[0]["data"]["number"] == MOBILE
    assert fake.calls[0]["data"]["message"] == notify.sms_text("Juan Dela Cruz", ENTRY_TS)
    assert fake.calls[0]["timeout"] == 5
