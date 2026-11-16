"""The notification_log statements against a real Postgres (PC-020, PC-021).

Skipped unless TEST_DB_DSN names a scratch database, for example:

    TEST_DB_DSN="postgresql://attendance:attendance@localhost:5433/attendance_test" \\
        python -m pytest tests/test_notification_db.py

It creates the schema there and deletes the rows it wrote. It refuses a database
called `attendance`, which is the live one.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

DSN = os.environ.get("TEST_DB_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DB_DSN is not set")

UID = "PC020TEST"


@pytest.fixture
def db(monkeypatch):
    from backend import db as real_db

    name = DSN.rsplit("/", 1)[-1].split("?")[0]
    if "dbname=" in DSN:
        name = DSN.split("dbname=")[1].split()[0]
    assert name != "attendance", "TEST_DB_DSN points at the live database"

    monkeypatch.setattr(real_db, "DB_DSN", DSN)
    real_db.init_db()
    real_db.init_db()  # the schema is re-run on every start; it has to survive that
    yield real_db
    with real_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE uid = %s", (UID,))


def entry(db):
    return db.insert_log(uid=UID, student_id=None, method="nfc", status="accepted")


def test_one_row_per_entry_and_channel(db):
    log = entry(db)

    first = db.insert_notification(log["id"], "email", log["ts"])
    again = db.insert_notification(log["id"], "email", log["ts"])
    other = db.insert_notification(log["id"], "sms", log["ts"], "DISABLED", "channel off")

    assert first["status"] == "PENDING" and first["t0"] == log["ts"]
    assert again is None
    assert (other["status"], other["error"]) == ("DISABLED", "channel off")


def test_a_row_is_claimed_by_one_attempt_at_a_time(db):
    log = entry(db)
    row = db.insert_notification(log["id"], "email", log["ts"])

    assert db.claim_notification(row["id"]) is True
    assert db.claim_notification(row["id"]) is False

    db.release_notification(row["id"], error="SMTPServerDisconnected")
    assert db.claim_notification(row["id"]) is True

    (kept,) = [n for n in db.get_notifications() if n["id"] == row["id"]]
    assert kept["attempts"] == 2
    assert kept["status"] == "PENDING"


def test_delivered_stamps_t1_and_the_latency_since_the_entry(db):
    log = entry(db)
    row = db.insert_notification(log["id"], "email", log["ts"])
    db.claim_notification(row["id"])

    done = db.finish_notification(row["id"], "DELIVERED", provider_message_id="abc123")

    assert done["status"] == "DELIVERED"
    assert done["provider_message_id"] == "abc123"
    assert done["t1"] >= done["t0"]
    assert done["latency_ms"] == round((done["t1"] - done["t0"]).total_seconds() * 1000)
    assert db.finish_notification(row["id"], "FAILED") is None  # closed rows stay closed
    assert db.claim_notification(row["id"]) is False


def test_latency_is_measured_from_the_entry_not_from_the_send(db):
    log = entry(db)
    earlier = log["ts"] - timedelta(seconds=30)
    row = db.insert_notification(log["id"], "email", earlier)

    done = db.finish_notification(row["id"], "DELIVERED")

    assert 30_000 <= done["latency_ms"] < 40_000


def test_failed_keeps_the_error_and_has_no_latency(db):
    log = entry(db)
    row = db.insert_notification(log["id"], "email", log["ts"])

    done = db.finish_notification(row["id"], "FAILED", error="SMTPRecipientsRefused 550")

    assert (done["status"], done["error"]) == ("FAILED", "SMTPRecipientsRefused 550")
    assert done["t1"] is None and done["latency_ms"] is None


def test_rows_go_when_their_entry_is_deleted(db):
    log = entry(db)
    row = db.insert_notification(log["id"], "email", log["ts"])

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attendance_logs WHERE id = %s", (log["id"],))

    assert row["id"] not in [n["id"] for n in db.get_notifications()]


def test_the_export_can_be_cut_by_date(db):
    log = entry(db)
    row = db.insert_notification(log["id"], "email", log["ts"])
    today = datetime.now(timezone.utc).astimezone().date()
    far = (today + timedelta(days=30)).isoformat()

    assert row["id"] not in [n["id"] for n in db.get_notifications(date_from=far)]
    assert row["id"] in [n["id"] for n in db.get_notifications(date_to=far)]


def test_pending_rows_are_read_back_with_what_is_needed_to_send_them(db):
    db.insert_student("PC020-S1", UID, name="Queued Student",
                      guardian_email="queued@example.com", guardian_mobile="09170000002")
    try:
        log = db.insert_log(uid=UID, student_id="PC020-S1", method="nfc", status="accepted")
        other = entry(db)  # a card with no roster row
        waiting = db.insert_notification(log["id"], "email", log["ts"])
        in_flight = db.insert_notification(log["id"], "sms", log["ts"])
        db.claim_notification(in_flight["id"])
        done = db.insert_notification(other["id"], "email", other["ts"])
        db.claim_notification(done["id"])
        db.finish_notification(done["id"], "DELIVERED")
        db.insert_notification(other["id"], "sms", other["ts"], "DISABLED", "channel off")

        mine = {r["id"]: r for r in db.pending_notifications() if r["log_id"] == log["id"]}
        ids = {r["id"] for r in db.pending_notifications()}

        assert set(mine) == {waiting["id"], in_flight["id"]}
        assert done["id"] not in ids
        row = mine[waiting["id"]]
        assert (row["channel"], row["t0"], row["claimed_at"]) == ("email", log["ts"], None)
        assert (row["name"], row["guardian_email"], row["guardian_mobile"]) == (
            "Queued Student", "queued@example.com", "09170000002")
        assert mine[in_flight["id"]]["claimed_at"] is not None
    finally:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_logs WHERE uid = %s", (UID,))
                cur.execute("DELETE FROM students WHERE student_id = 'PC020-S1'")


def test_a_guard_pick_is_kept_on_the_review_row_and_goes_with_an_erase(db):
    """PC-031 on a real Postgres: only a tailgating row takes a pick, the pick must be
    on the roster, and erasing that student clears it (ON DELETE SET NULL)."""
    db.insert_student("PC031-S1", "PC031AA01", name="Picked Student")
    try:
        face = db.insert_log(uid=UID, student_id=None, method="face", status="tailgating")
        other = db.insert_log(uid=UID, student_id=None, method="nfc", status="mismatch")
        alert = db.insert_review(face["id"], None, "tailgating", "face with no tap")["id"]
        wrong = db.insert_review(other["id"], None, "mismatch", None)["id"]

        with pytest.raises(LookupError):
            db.resolve_review(alert, "identified", "guard", identified_as="PC031-NOBODY")
        with pytest.raises(ValueError):
            db.resolve_review(wrong, "identified", "guard", identified_as="PC031-S1")

        row = db.resolve_review(alert, "identified", "guard", identified_as="PC031-S1")
        assert (row["identified_as"], row["resolved_by"]) == ("PC031-S1", "guard")
        assert row["resolved_at"] is not None

        db.delete_student("PC031-S1")
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT identified_as, resolution FROM review_queue WHERE id = %s",
                            (alert,))
                assert cur.fetchone() == (None, "identified")
    finally:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_logs WHERE uid = %s", (UID,))
                cur.execute("DELETE FROM students WHERE student_id = 'PC031-S1'")
