"""What a guardian is sent and when (PC-022, PC-023), and what the notification log
keeps of it (PC-020). No SMTP server and no database are reached: every test that lets
a message out replaces `notify._send` with a recorder, and the log is the in-memory
fake.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend import db, decision, notify

MANILA = timezone(timedelta(hours=8))
# 7:12 AM on Nov 24, 2026 in Manila, as the database hands it over (UTC).
ENTRY_TS = datetime(2026, 11, 23, 23, 12, tzinfo=timezone.utc)
APPROVED_SAMPLE = (
    "SAFEHSCI: Juan Dela Cruz entered the Hua Siong College of Iloilo main guardpost "
    "on Nov 24, 2026 at 7:12 AM."
)


@pytest.fixture(autouse=True)
def school_settings(monkeypatch, fake_db):
    """Pin what the environment could change, and keep the log in memory."""
    fake_db.patch_notifications(monkeypatch, db)
    monkeypatch.setattr(notify, "SCHOOL_ZONE", MANILA)
    monkeypatch.setattr(notify, "ENTRY_POINT", "main guardpost")
    monkeypatch.setattr(notify, "SMS_SENDER", "SAFEHSCI")


def student(**over):
    row = {
        "student_id": "S-2026-0042",
        "uid": "04A1B2C3",
        "name": "Juan Dela Cruz",
        "guardian_email": "guardian@example.com",
        "guardian_mobile": "09171234567",
    }
    row.update(over)
    return row


def log(status=decision.ACCEPTED, **over):
    row = {
        "id": 7,
        "uid": "04A1B2C3",
        "student_id": "S-2026-0042",
        "ts": ENTRY_TS,
        "method": "nfc",
        "status": status,
        "face_score": 0.8123,
        "face_match": True,
        "liveness_score": 0.9456,
        "liveness_pass": True,
    }
    row.update(over)
    return row


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "EMAIL_ENABLED", True)
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify, "SMTP_FROM", "safe@example.com")
    monkeypatch.setattr(notify, "_send", sent.append)
    return sent


# --- the SMS text (PC-023) ---


def test_the_sms_is_the_sample_the_sender_name_was_approved_with():
    assert notify.sms_text("Juan Dela Cruz", ENTRY_TS) == APPROVED_SAMPLE


def test_the_sms_starts_with_the_sender_name():
    assert notify.sms_text("Juan Dela Cruz", ENTRY_TS).startswith("SAFEHSCI: ")


def test_the_date_and_time_are_the_schools_not_the_databases(monkeypatch):
    # 23:12 UTC on the 23rd is the morning of the 24th in Manila.
    assert notify.when_text(ENTRY_TS) == ("Nov 24, 2026", "7:12 AM")

    monkeypatch.setattr(notify, "SCHOOL_ZONE", timezone.utc)
    assert notify.when_text(ENTRY_TS) == ("Nov 23, 2026", "11:12 PM")


@pytest.mark.parametrize(
    "hour, minute, expected",
    [(0, 5, "12:05 AM"), (7, 0, "7:00 AM"), (12, 0, "12:00 PM"), (13, 9, "1:09 PM")],
)
def test_the_time_is_written_on_a_12_hour_clock(hour, minute, expected):
    ts = datetime(2026, 11, 24, hour, minute, tzinfo=MANILA)
    assert notify.when_text(ts)[1] == expected


def test_an_unknown_time_zone_falls_back_to_this_machines():
    assert notify._zone("No/Such_Zone") is None
    assert notify._zone("") is None


def test_the_entry_point_is_a_setting(monkeypatch):
    monkeypatch.setattr(notify, "ENTRY_POINT", "east gate")
    assert "Hua Siong College of Iloilo east gate on" in notify.sms_text("Juan", ENTRY_TS)


def test_a_long_name_is_shortened_to_given_name_and_surname():
    name = "Maria Clara Esperanza Concepcion Dolores De Los Santos Villanueva Macaraeg"
    text = notify.sms_text(name, ENTRY_TS)

    assert len(text) <= notify.SMS_MAX_CHARS
    assert text.startswith("SAFEHSCI: Maria Macaraeg entered ")
    assert text.endswith("on Nov 24, 2026 at 7:12 AM.")


def test_a_name_still_too_long_is_cut_and_the_date_and_time_are_kept():
    name = "Bartholomew" * 6 + " " + "Villanueva" * 6
    text = notify.sms_text(name, ENTRY_TS)

    assert len(text) == notify.SMS_MAX_CHARS
    assert "... entered the Hua Siong College of Iloilo main guardpost" in text
    assert text.endswith("on Nov 24, 2026 at 7:12 AM.")


def test_a_name_that_fits_is_never_shortened():
    name = "Maria Clara De Los Santos"
    assert f": {name} entered " in notify.sms_text(name, ENTRY_TS)


@pytest.mark.parametrize("name", [None, "", "   "])
def test_a_student_without_a_name_is_still_announced(name):
    assert notify.sms_text(name, ENTRY_TS).startswith("SAFEHSCI: Your student entered ")


def test_no_sms_text_starts_with_the_word_the_provider_drops():
    # Semaphore silently ignores a message that starts with TEST.
    assert not notify.sms_text("TEST Student", ENTRY_TS).upper().startswith("TEST")


# --- the email (PC-023) ---


def test_the_email_carries_the_same_sentence_as_the_sms(outbox):
    notify.notify(student(), log())

    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == "guardian@example.com"
    assert msg["From"] == "safe@example.com"
    assert APPROVED_SAMPLE.removeprefix("SAFEHSCI: ") in msg.get_content()


def test_the_email_holds_nothing_but_name_date_time_and_entry_point(outbox):
    notify.notify(
        student(),
        log(status=decision.FLAGGED, face_match=False, liveness_pass=False),
    )

    text = (outbox[0]["Subject"] + "\n" + outbox[0].get_content()).lower()
    for private in (
        "s-2026-0042",  # student ID
        "04a1b2c3",  # card UID
        "09171234567",  # guardian mobile
        "nfc",  # method
        "flagged",  # status
        "0.8123",  # face score
        "0.9456",  # liveness score
        "mismatch",
        "spoof",
        "warning",
        "denied",
    ):
        assert private not in text


# --- which taps reach a guardian (PC-022) ---


@pytest.mark.parametrize("status", [decision.ACCEPTED, decision.FLAGGED])
def test_an_entry_that_counts_is_sent(outbox, status):
    assert decision.counts_as_present(status)

    notify.notify(student(), log(status=status))

    assert len(outbox) == 1


@pytest.mark.parametrize(
    "status",
    [
        decision.REJECTED,
        decision.NO_FACE,
        decision.MISMATCH,
        decision.SPOOF,
        decision.TAILGATING,
    ],
)
def test_a_tap_that_does_not_count_sends_nothing(outbox, status):
    notify.notify(student(), log(status=status))

    assert outbox == []


def test_the_gate_follows_the_attendance_rule(outbox):
    """Whatever decision.py stops counting stops notifying, with no list kept here."""
    for status in decision.not_counted_statuses():
        notify.notify(student(), log(status=status))

    assert outbox == []


def test_an_unregistered_card_sends_nothing(outbox):
    notify.notify(None, log(status=decision.UNREGISTERED, student_id=None))

    assert outbox == []


def test_a_tap_with_no_status_sends_nothing(outbox):
    notify.notify(student(), log(status=None))

    assert outbox == []


def test_a_student_with_no_guardian_email_sends_nothing(outbox):
    notify.notify(student(guardian_email=None), log())

    assert outbox == []


def test_email_switched_off_sends_nothing(outbox, monkeypatch):
    monkeypatch.setattr(notify, "EMAIL_ENABLED", False)

    notify.notify(student(), log())

    assert outbox == []


def test_a_failed_send_is_swallowed_and_does_not_print_the_address(
    outbox, monkeypatch, capsys
):
    def refuse(msg):
        raise RuntimeError("550 no such user guardian@example.com")

    monkeypatch.setattr(notify, "_send", refuse)

    notify.notify(student(), log())  # must not raise

    assert "guardian@example.com" not in capsys.readouterr().out


def test_the_operator_console_still_reports_a_denied_tap(outbox, capsys):
    notify.notify(student(), log(status=decision.REJECTED, face_match=False))

    line = capsys.readouterr().out
    assert "[REJECTED]" in line
    assert "FACE MISMATCH" in line
    assert outbox == []


# --- the notification log (PC-020) ---


def rows(fake_db, channel=None):
    return [n for n in fake_db.notifications if channel in (None, n["channel"])]


def test_a_sent_email_is_logged_delivered_with_its_latency(outbox, fake_db):
    notify.notify(student(), log())

    (row,) = rows(fake_db, "email")
    assert row["status"] == notify.DELIVERED
    assert row["log_id"] == 7
    assert row["t0"] == ENTRY_TS  # the entry's own time, not the send time
    assert row["t1"] > row["t0"]
    assert row["latency_ms"] == 2000
    assert row["attempts"] == 1
    assert row["error"] is None


def test_every_entry_gets_one_row_per_channel(outbox, fake_db):
    notify.notify(student(), log())

    assert sorted(n["channel"] for n in fake_db.notifications) == ["email", "sms"]


def test_a_failed_send_is_logged_failed_with_the_kind_of_error_only(
    outbox, fake_db, monkeypatch
):
    def refuse(msg):
        raise RuntimeError("550 no such user guardian@example.com")

    monkeypatch.setattr(notify, "_send", refuse)

    notify.notify(student(), log())

    (row,) = rows(fake_db, "email")
    assert row["status"] == notify.FAILED
    assert row["error"] == "RuntimeError"
    assert row["t1"] is None and row["latency_ms"] is None


def test_the_same_entry_is_never_sent_twice(outbox, fake_db):
    notify.notify(student(), log())
    notify.notify(student(), log())  # a retry or a duplicate call for log 7

    assert len(outbox) == 1
    assert len(rows(fake_db, "email")) == 1


def test_a_second_entry_by_the_same_student_gets_its_own_message(outbox, fake_db):
    notify.notify(student(), log(id=7))
    notify.notify(student(), log(id=8))

    assert len(outbox) == 2
    assert [n["log_id"] for n in rows(fake_db, "email")] == [7, 8]


def test_a_row_someone_else_claimed_is_not_sent(outbox, fake_db, monkeypatch):
    monkeypatch.setattr(db, "claim_notification", lambda notification_id: False)

    notify.notify(student(), log())

    assert outbox == []


def test_nothing_is_sent_when_the_row_cannot_be_written(outbox, monkeypatch, capsys):
    """No row, no message: a send the log does not know of could not be counted and
    could be repeated."""
    def down(*args, **kwargs):
        raise ConnectionError("postgres is down for guardian@example.com")

    monkeypatch.setattr(db, "insert_notification", down)

    notify.notify(student(), log())  # must not raise

    assert outbox == []
    out = capsys.readouterr().out
    assert "not recorded" in out
    assert "guardian@example.com" not in out


@pytest.mark.parametrize(
    "setting, value, reason",
    [
        ("EMAIL_ENABLED", False, "NOTIFY_EMAIL_ENABLED is off"),
        ("SMTP_HOST", "", "SMTP_HOST is not set"),
    ],
)
def test_a_channel_that_is_off_is_logged_disabled(
    outbox, fake_db, monkeypatch, setting, value, reason
):
    monkeypatch.setattr(notify, setting, value)

    notify.notify(student(), log())

    (row,) = rows(fake_db, "email")
    assert (row["status"], row["error"]) == (notify.DISABLED, reason)
    assert outbox == []


def test_a_student_with_no_guardian_email_is_logged_disabled(outbox, fake_db):
    notify.notify(student(guardian_email=None), log())

    (row,) = rows(fake_db, "email")
    assert (row["status"], row["error"]) == (notify.DISABLED, notify.NO_RECIPIENT)


def test_sms_is_logged_disabled_until_the_sender_is_built(outbox, fake_db, monkeypatch):
    notify.notify(student(), log(id=7))
    monkeypatch.setattr(notify, "SMS_ENABLED", True)
    notify.notify(student(), log(id=8))

    first, second = rows(fake_db, "sms")
    assert (first["status"], first["error"]) == (notify.DISABLED, "NOTIFY_SMS_ENABLED is off")
    assert (second["status"], second["error"]) == (
        notify.DISABLED, "the SMS sender is not built")


def test_one_channel_failing_does_not_stop_the_other(outbox, fake_db, monkeypatch):
    real = fake_db.insert_notification

    def email_row_fails(log_id, channel, *args, **kwargs):
        if channel == "email":
            raise ConnectionError("simulated")
        return real(log_id, channel, *args, **kwargs)

    monkeypatch.setattr(db, "insert_notification", email_row_fails)

    notify.notify(student(), log())

    assert [n["channel"] for n in fake_db.notifications] == ["sms"]


def test_a_tap_that_does_not_count_leaves_no_row(outbox, fake_db):
    for status in decision.not_counted_statuses():
        notify.notify(student(), log(status=status))

    assert fake_db.notifications == []


def test_the_log_holds_no_student_id_and_no_contact(outbox, fake_db):
    notify.notify(student(), log())
    notify.notify(student(guardian_email=None), log(id=8))

    kept = repr(fake_db.notifications).lower()
    for private in ("s-2026-0042", "04a1b2c3", "guardian@example.com", "09171234567",
                    "juan"):
        assert private not in kept
