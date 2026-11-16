"""What a guardian is sent and when (PC-022, PC-023). No SMTP server is reached: every
test that lets a message out replaces `notify._send` with a recorder.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend import decision, notify

MANILA = timezone(timedelta(hours=8))
# 7:12 AM on Nov 24, 2026 in Manila, as the database hands it over (UTC).
ENTRY_TS = datetime(2026, 11, 23, 23, 12, tzinfo=timezone.utc)
APPROVED_SAMPLE = (
    "SAFEHSCI: Juan Dela Cruz entered the Hua Siong College of Iloilo main guardpost "
    "on Nov 24, 2026 at 7:12 AM."
)


@pytest.fixture(autouse=True)
def school_settings(monkeypatch):
    """Pin what the environment could change."""
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
