"""PC-024: a card reported lost marks nobody present and cannot go to another student.

Driven through the API with the in-memory database in conftest.py. The real statements
are checked against a scratch database at the end (TEST_DB_DSN)."""

import os

import pytest

from backend import db, decision

OLD, NEW, OTHER = "C3BE343A", "D4CF454B", "E5D0565C"


def student(uid=OLD, sid="S001", name="Test Student"):
    return {"student_id": sid, "uid": uid, "name": name, "guardian_email": "g@example.com",
            "guardian_mobile": "09171234567", "face_embedding": [0.1, 0.2, 0.3],
            "embed_model": "buffalo_l", "face_consent": False}


def tap(client, uid):
    return client.post("/tap", json={"uid": uid}).json()


def test_a_lost_card_is_logged_revoked_under_its_owner_and_reviewed(client, fake_db, sinks):
    fake_db.add_student(student())
    assert client.post("/api/students/S001/card/lost").status_code == 200

    body = tap(client, OLD)

    log = fake_db.logs[-1]
    assert log["status"] == decision.REVOKED and log["student_id"] == "S001"
    assert not decision.counts_as_present(log["status"])
    assert fake_db.reviews[-1]["reason"] == "card reported lost"
    assert body["student"]["name"] == "Test Student"
    assert fake_db.notifications == []  # no guardian message
    lost = [a for a in fake_db.audits if a["action"] == "card_lost"]
    assert [a["target"] for a in lost] == ["S001"]
    assert OLD not in str(fake_db.audits)  # no card UID in the audit log (PC-044)


def test_a_lost_card_does_not_reach_the_matcher(client, fake_db, fake_matcher, monkeypatch):
    from backend import perception

    monkeypatch.setattr(perception, "PERCEPTION_ENABLED", True)
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")

    tap(client, OLD)

    assert fake_matcher.taps == []
    assert fake_db.logs[-1]["status"] == decision.REVOKED


def test_a_new_card_works_and_the_old_one_stays_revoked(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    r = client.post("/api/students/S001/card", json={"uid": NEW.lower()})
    assert r.status_code == 200 and r.json()["uid"] == NEW

    assert tap(client, NEW)["log"]["status"] != decision.REVOKED
    assert tap(client, OLD)["log"]["status"] == decision.REVOKED


def test_a_new_card_while_the_old_one_is_still_on_file_revokes_the_old_one(client, fake_db):
    fake_db.add_student(student())
    r = client.post("/api/students/S001/card", json={"uid": NEW})
    assert r.json()["revoked_old"] is True
    assert fake_db.audits[-1]["detail"] == "old card reported lost"
    assert tap(client, OLD)["log"]["status"] == decision.REVOKED


def test_found_gives_the_card_back(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    r = client.post("/api/students/S001/card/found")
    assert r.status_code == 200 and r.json()["uid"] == OLD
    assert tap(client, OLD)["log"]["status"] != decision.REVOKED


def test_found_is_refused_once_the_student_has_a_new_card(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    client.post("/api/students/S001/card", json={"uid": NEW})
    assert client.post("/api/students/S001/card/found").status_code == 409


def test_a_lost_card_cannot_be_put_on_another_student(client, fake_db):
    fake_db.add_student(student())
    fake_db.add_student(student(uid=OTHER, sid="S002", name="Other"))
    client.post("/api/students/S001/card/lost")

    assert client.post("/api/students/S002/card", json={"uid": OLD}).status_code == 409
    assert client.post("/api/students", json={"student_id": "S003", "uid": OLD}).status_code == 409


def test_a_card_on_another_student_is_refused(client, fake_db):
    fake_db.add_student(student())
    fake_db.add_student(student(uid=OTHER, sid="S002", name="Other"))
    assert client.post("/api/students/S001/card", json={"uid": OTHER}).status_code == 409


@pytest.mark.parametrize("path", ["card/lost", "card/found"])
def test_unknown_student_is_404(client, path):
    assert client.post(f"/api/students/NOPE/{path}").status_code == 404


def test_lost_twice_and_found_without_a_lost_card_are_refused(client, fake_db):
    fake_db.add_student(student())
    assert client.post("/api/students/S001/card/found").status_code == 409  # has a card
    client.post("/api/students/S001/card/lost")
    assert client.post("/api/students/S001/card/lost").status_code == 409
    fake_db.add_student(student(uid=OTHER, sid="S002", name="Other"))
    client.post("/api/students/S002/card/lost")
    client.post("/api/students/S002/card/found")
    client.post("/api/students/S002/card/lost")
    del fake_db.revoked[OTHER]
    assert client.post("/api/students/S002/card/found").status_code == 404


def test_the_roster_shows_a_student_between_cards(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    rows = client.get("/api/students").json()["students"]
    assert rows[0]["uid"] is None and rows[0]["lost_cards"] == 1


def test_erase_takes_the_lost_cards_and_their_taps(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    tap(client, OLD)
    client.post("/api/students/S001/card", json={"uid": NEW})

    assert client.delete("/api/students/S001").status_code == 200

    assert fake_db.revoked == {} and fake_db.logs == []
    assert all(OLD not in str(a) and NEW not in str(a) for a in fake_db.audits)


# --- the real statements ---

DSN = os.environ.get("TEST_DB_DSN", "")


@pytest.mark.skipif(not DSN, reason="TEST_DB_DSN is not set")
def test_lost_cards_on_a_real_database(monkeypatch):
    name = DSN.split("dbname=")[1].split()[0] if "dbname=" in DSN else (
        DSN.rsplit("/", 1)[-1].split("?")[0])
    assert name != "attendance", "TEST_DB_DSN points at the live database"
    monkeypatch.setattr(db, "DB_DSN", DSN)
    db.init_db()
    sid, other = "PC024-S1", "PC024-S2"
    a, b, c = "PC024AA01", "PC024AA02", "PC024AA03"

    def cleanup():
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_logs WHERE uid LIKE 'PC024%'")
                cur.execute("DELETE FROM students WHERE student_id LIKE 'PC024%'")
                cur.execute("DELETE FROM audit_log WHERE actor = 'pc024-test'")

    cleanup()
    try:
        db.insert_student(sid, a, name="Lost Card")
        db.insert_student(other, c, name="Other")
        assert db.mark_card_lost(sid, "pc024-test")["uid"] is None
        assert db.find_revoked_card(a) == {"student_id": sid, "name": "Lost Card"}
        assert db.find_student_by_uid(a) is None
        with pytest.raises(ValueError):
            db.mark_card_lost(sid, "pc024-test")
        with pytest.raises(db.CardConflict):
            db.insert_student("PC024-S3", a)
        with pytest.raises(db.CardConflict):
            db.update_student(other, uid=a)
        with pytest.raises(db.CardConflict):
            db.link_card(other, a, "pc024-test")
        assert db.mark_card_found(sid)["uid"] == a
        assert db.find_revoked_card(a) is None
        assert db.link_card(sid, b, "pc024-test")["revoked_old"] is True
        with pytest.raises(ValueError):
            db.mark_card_found(sid)
        row = next(s for s in db.get_students() if s["student_id"] == sid)
        assert row["uid"] == b and row["lost_cards"] == 1
        db.insert_log(uid=a, student_id=sid, method="nfc", status=decision.REVOKED)
        db.insert_log(uid=a, student_id=None, method="nfc", status=decision.UNREGISTERED)

        counts = db.delete_student(sid, "pc024-test")

        assert counts["students"] == 1 and counts["logs"] == 2 and counts["old_uids"] == [a]
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM revoked_cards WHERE uid LIKE 'PC024%'")
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT count(*) FROM attendance_logs WHERE uid IN (%s, %s)", (a, b))
                assert cur.fetchone()[0] == 0
    finally:
        cleanup()
