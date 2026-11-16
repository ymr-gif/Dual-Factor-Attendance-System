"""Guardian contacts (PC-019): what is accepted, what is stored, and the test message
a saved contact gets. No SMTP server is reached; `conftest.py` forbids `notify._send`
and the tests that need a send replace it.
"""

from email.message import EmailMessage

import pytest

from backend import contacts, notify


# --- formats -----------------------------------------------------------------


@pytest.mark.parametrize(
    "typed",
    [
        "09171234567",
        "+639171234567",
        "0917 123 4567",
        "0917-123-4567",
        "+63 917 123 4567",
        "(0917) 123.4567",
        "  09171234567\n",
    ],
)
def test_a_philippine_mobile_is_stored_in_one_form(typed):
    assert contacts.normalize_mobile(typed) == "09171234567"


@pytest.mark.parametrize("typed", [None, "", "   ", "-"])
def test_a_blank_mobile_is_no_mobile(typed):
    assert contacts.normalize_mobile(typed) is None


@pytest.mark.parametrize(
    "typed",
    [
        "0917123456",  # one digit short
        "091712345678",  # one digit long
        "639171234567",  # country code without the plus
        "9171234567",  # no leading 0
        "08171234567",  # not a mobile prefix
        "+6391712345678",
        "+19171234567",  # another country
        "0917123456a",
        "033 337 1234",  # an Iloilo landline
        "call me",
    ],
)
def test_a_number_that_is_not_a_philippine_mobile_is_refused(typed):
    with pytest.raises(ValueError) as refused:
        contacts.normalize_mobile(typed)
    assert typed not in str(refused.value), "the message must not repeat what was typed"


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("guardian@example.com", "guardian@example.com"),
        ("  guardian@example.com ", "guardian@example.com"),
        ("first.last+tag@mail.example.ph", "first.last+tag@mail.example.ph"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_email_is_trimmed_and_a_blank_one_is_none(typed, stored):
    assert contacts.normalize_email(typed) == stored


@pytest.mark.parametrize(
    "typed",
    [
        "parent",
        "guardian@",
        "@mail.example.ph",
        "guardian@example",
        "guardian@@example.com",
        "guardian @example.com",
        "guardian@example..com",
        "a@b.c" + "x" * 254,
    ],
)
def test_an_address_that_cannot_be_one_is_refused(typed):
    with pytest.raises(ValueError) as refused:
        contacts.normalize_email(typed)
    assert typed not in str(refused.value)


# --- the roster endpoints ----------------------------------------------------


def create(client, **fields):
    return client.post("/api/students", json={"student_id": "s001", "uid": "c3be343a", **fields})


def test_a_new_student_keeps_the_mobile_in_its_stored_form(client, fake_db):
    response = create(client, guardian_mobile="+63 917 123 4567")

    assert response.status_code == 200
    assert response.json()["guardian_mobile"] == "09171234567"
    assert fake_db.students["C3BE343A"]["guardian_mobile"] == "09171234567"


def test_the_mobile_is_optional(client, fake_db):
    response = create(client, name="Test Student")

    assert response.status_code == 200
    assert response.json()["guardian_mobile"] is None
    assert response.json()["contact_test"] == {}


@pytest.mark.parametrize(
    "fields",
    [{"guardian_mobile": "0917123456"}, {"guardian_email": "guardian@example"}],
)
def test_a_bad_contact_is_refused_and_nothing_is_saved(client, fake_db, fields):
    response = create(client, **fields)

    assert response.status_code == 422
    assert "must look like" in response.json()["detail"]
    assert fake_db.students == {}
    assert fake_db.audits == []


def test_an_update_normalizes_and_refuses_the_same_way(client, fake_db):
    create(client)

    assert client.patch("/api/students/S001", json={"guardian_mobile": "12345"}).status_code == 422
    assert fake_db.students["C3BE343A"]["guardian_mobile"] is None

    response = client.patch("/api/students/S001", json={"guardian_mobile": "0917-123-4567"})
    assert response.status_code == 200
    assert response.json()["guardian_mobile"] == "09171234567"


def test_the_roster_lists_the_mobile(client, fake_db):
    create(client, guardian_mobile="09171234567")

    assert client.get("/api/students").json()["students"][0]["guardian_mobile"] == "09171234567"


# --- the test message on save ------------------------------------------------


def test_saving_contacts_reports_a_test_per_channel(client, fake_db):
    response = create(client, guardian_email="guardian@example.com", guardian_mobile="09171234567")

    # Email is off in tests and the SMS sender is not switched on: both are skipped,
    # and said to be, rather than passed over in silence.
    assert response.json()["contact_test"] == {
        "email": "email test skipped (NOTIFY_EMAIL_ENABLED is off)",
        "sms": "SMS test skipped",
    }


def test_the_audit_row_for_a_contact_test_holds_no_contact(client, fake_db):
    create(client, guardian_email="guardian@example.com", guardian_mobile="09171234567")

    rows = [a for a in fake_db.audits if a["action"] == "contact_test"]
    assert len(rows) == 1
    assert rows[0]["target"] == "S001"
    assert "SMS test skipped" in rows[0]["detail"]
    for row in fake_db.audits:
        assert "guardian@example.com" not in str(row)
        assert "09171234567" not in str(row)


def test_an_update_tests_only_the_contact_it_saved(client, fake_db):
    create(client, guardian_email="guardian@example.com")

    response = client.patch("/api/students/S001", json={"guardian_mobile": "09171234567"})

    assert response.json()["contact_test"] == {"sms": "SMS test skipped"}
    assert client.patch("/api/students/S001", json={"name": "New Name"}).json()["contact_test"] == {}


@pytest.fixture
def smtp(monkeypatch):
    """Email switched on, with `_send` replaced by a recorder."""
    sent = []
    monkeypatch.setattr(notify, "EMAIL_ENABLED", True)
    monkeypatch.setattr(notify, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(notify, "SMTP_FROM", "safe@example.com")
    monkeypatch.setattr(notify, "_send", sent.append)
    return sent


def test_a_saved_email_gets_one_test_message(client, fake_db, smtp):
    response = create(client, guardian_email="guardian@example.com")

    assert response.json()["contact_test"] == {"email": "email test sent"}
    assert len(smtp) == 1
    message = smtp[0]
    assert isinstance(message, EmailMessage)
    assert message["To"] == "guardian@example.com"
    # A contact check says nothing about the student.
    text = message["Subject"] + message.get_content()
    assert "S001" not in text and "C3BE343A" not in text


def test_a_failed_test_message_still_saves_the_student(client, fake_db, smtp, monkeypatch):
    def refuse(message):
        raise ConnectionRefusedError("could not reach guardian@example.com's server")

    monkeypatch.setattr(notify, "_send", refuse)

    response = create(client, guardian_email="guardian@example.com")

    assert response.status_code == 200
    assert response.json()["contact_test"] == {"email": "email test failed: ConnectionRefusedError"}
    assert "C3BE343A" in fake_db.students


def test_email_on_without_a_host_is_reported_not_attempted(client, fake_db, smtp, monkeypatch):
    monkeypatch.setattr(notify, "SMTP_HOST", "")

    response = create(client, guardian_email="guardian@example.com")

    assert response.json()["contact_test"] == {"email": "email test skipped (SMTP_HOST is not set)"}
    assert smtp == []
