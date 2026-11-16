"""Erasing a student (PC-044): after it, the student ID and the card UID are nowhere
the system wrote them. The last test runs the real statements and dumps every table;
it needs TEST_DB_DSN to name a scratch database (see tests/test_notification_db.py).
"""

import json
import os

import pytest

from backend import db, privacy

SID, UID = "S-2026-0042", "04A1B2C3"
OTHER_SID, OTHER_UID = "S-2026-0420", "04A1B2C399"


# --- which lines name a student ---


@pytest.mark.parametrize(
    "text",
    [
        "3 shot(s), buffalo_l; dup?~S-2026-0042@0.912",
        "tailgating; nearest=S-2026-0042",
        "uid=04A1B2C3",
        "uid=04a1b2c3",
    ],
)
def test_a_student_is_found_in_the_forms_the_code_writes(text):
    assert db.names_student(text, SID, UID)


@pytest.mark.parametrize(
    "text, sid, uid",
    [
        ("3 shot(s), buffalo_l; dup?~S-2026-00421@0.912", SID, UID),  # a longer ID
        ("3 shot(s), buffalo_l; dup?~XS-2026-0042@0.912", SID, UID),
        ("tailgating; nearest=S-2026-00421", SID, UID),
        ("uid=04A1B2C399", SID, UID),
        # An ID that is also a word or a number the system writes elsewhere.
        ("email test sent; SMS test skipped", "TEST", "04A1B2C3"),
        ("3 shot(s), buffalo_l", "3", "04A1B2C3"),
        ("logs=3 students=1 notifications=0 audit_rows=2", "3", "04A1B2C3"),
        ("granted", "GRANTED", None),
        ("uid=04A1B2C3", SID, None),
        (None, SID, UID),
        ("anything", "", UID),
    ],
)
def test_nothing_else_counts_as_naming_the_student(text, sid, uid):
    assert not db.names_student(text, sid, uid)


# --- the failed-tap queue ---


def queue(tmp_path, lines):
    path = tmp_path / "failed_taps.jsonl"
    path.write_text("".join(line + "\n" for line in lines))
    return str(path)


def test_the_erased_cards_queued_taps_are_dropped_and_the_rest_kept(tmp_path):
    path = queue(tmp_path, [
        json.dumps({"uid": UID, "queued_at": 1.0}),
        json.dumps({"uid": OTHER_UID, "queued_at": 2.0}),
        json.dumps({"uid": UID.lower(), "queued_at": 3.0}),
    ])

    assert privacy.scrub_failed_taps(UID, path) == 2

    left = open(path).read()
    assert UID + '"' not in left and UID.lower() + '"' not in left
    assert json.loads(left)["uid"] == OTHER_UID
    assert os.listdir(tmp_path) == ["failed_taps.jsonl"]  # no temp file left behind


def test_a_line_that_cannot_be_read_goes_if_it_holds_the_uid(tmp_path):
    path = queue(tmp_path, ['{"uid": "04A1B2C3", "queued_at"', "not json at all"])

    assert privacy.scrub_failed_taps(UID, path) == 1
    assert open(path).read() == "not json at all\n"


def test_no_queue_file_and_no_uid_are_not_errors(tmp_path):
    assert privacy.scrub_failed_taps(UID, str(tmp_path / "missing.jsonl")) == 0
    path = queue(tmp_path, [json.dumps({"uid": UID, "queued_at": 1.0})])
    assert privacy.scrub_failed_taps(None, path) == 0
    assert privacy.scrub_failed_taps("", path) == 0


def test_a_queue_with_no_hit_is_left_untouched(tmp_path):
    path = queue(tmp_path, [json.dumps({"uid": OTHER_UID, "queued_at": 2.0})])
    before = os.stat(path).st_mtime_ns

    assert privacy.scrub_failed_taps(UID, path) == 0
    assert os.stat(path).st_mtime_ns == before


def test_a_queue_that_cannot_be_cleaned_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr(
        db, "delete_student",
        lambda student_id, actor=None: {"logs": 1, "students": 1, "notifications": 0,
                                        "audit_rows": 0, "uid": UID},
    )

    def locked(uid, path=None):
        raise PermissionError("failed_taps.jsonl")

    monkeypatch.setattr(privacy, "scrub_failed_taps", locked)

    counts = privacy.erase_student(SID)

    assert counts["queued_taps"] is None
    assert "uid" not in counts


# --- the endpoint ---


def add(fake_db, sid=SID, uid=UID):
    return fake_db.add_student({
        "student_id": sid, "uid": uid, "name": "Juan Dela Cruz",
        "guardian_email": "guardian@example.com", "guardian_mobile": "09171234567",
    })


def test_a_new_students_audit_row_does_not_hold_the_card_uid(client, fake_db):
    r = client.post("/api/students", json={"student_id": SID, "uid": UID, "name": "Juan"})

    assert r.status_code == 200
    (row,) = [a for a in fake_db.audits if a["action"] == "create"]
    assert UID not in repr(row)


def test_erase_removes_the_student_everywhere_and_names_nobody(client, fake_db, tmp_path):
    add(fake_db)
    add(fake_db, OTHER_SID, OTHER_UID)
    fake_db.insert_log(UID, None, "nfc", status="unregistered")  # before enrolment
    mine = fake_db.insert_log(UID, SID, "nfc", status="accepted")
    theirs = fake_db.insert_log(OTHER_UID, OTHER_SID, "nfc", status="accepted")
    fake_db.insert_notification(mine["id"], "email", mine["ts"])
    fake_db.insert_notification(theirs["id"], "email", theirs["ts"])
    fake_db.insert_review(mine["id"], SID, "flagged", "liveness fail on matched face")
    fake_db.insert_audit("op", "create", SID, f"uid={UID}")  # a row from before PC-044
    fake_db.insert_audit("op", "contact_test", SID, "email test sent")
    fake_db.insert_audit("op", "enroll", OTHER_SID, f"3 shot(s), buffalo_l; dup?~{SID}@0.912")
    fake_db.insert_audit("op", "update", OTHER_SID, None)
    (tmp_path / "failed_taps.jsonl").write_text(
        json.dumps({"uid": UID, "queued_at": 1.0}) + "\n"
        + json.dumps({"uid": OTHER_UID, "queued_at": 2.0}) + "\n"
    )

    r = client.delete(f"/api/students/{SID}")

    assert r.status_code == 200
    assert r.json() == {
        "erased": SID, "logs": 2, "students": 1, "notifications": 1, "audit_rows": 3,
        "queued_taps": 1,
    }
    kept = repr([fake_db.students, fake_db.logs, fake_db.notifications, fake_db.reviews,
                 fake_db.audits]) + (tmp_path / "failed_taps.jsonl").read_text()
    assert SID not in kept
    assert UID + "'" not in kept and UID + '"' not in kept

    # The other student is whole, apart from the note that named the erased one.
    assert OTHER_UID in fake_db.students
    assert [l["student_id"] for l in fake_db.logs] == [OTHER_SID]
    assert [n["log_id"] for n in fake_db.notifications] == [theirs["id"]]
    enroll = next(a for a in fake_db.audits if a["action"] == "enroll")
    assert (enroll["target"], enroll["detail"]) == (OTHER_SID, None)

    # The record that an erase happened: who did it and how much, not whom.
    erase = fake_db.audits[-1]
    assert (erase["action"], erase["target"]) == ("erase", None)
    assert erase["detail"] == "logs=2 students=1 notifications=1 audit_rows=3"


def test_erasing_someone_unknown_is_a_404_and_writes_no_audit_row(client, fake_db):
    r = client.delete("/api/students/NOBODY")

    assert r.status_code == 404
    assert fake_db.audits == []


def test_erase_can_be_run_again_to_clean_rows_left_by_an_older_erase(client, fake_db):
    # Before PC-044 the erase row itself held the student ID.
    fake_db.insert_audit("op", "erase", SID, "logs=4 students=1")

    r = client.delete(f"/api/students/{SID}")

    assert r.status_code == 200
    assert SID not in repr(fake_db.audits)


def audit_rows_of_others(fake_db):
    add(fake_db, OTHER_SID, OTHER_UID)
    fake_db.insert_audit("op", "contact_test", OTHER_SID, "email test sent; SMS test skipped")
    fake_db.insert_audit("op", "enroll", OTHER_SID, "3 shot(s), buffalo_l")
    fake_db.insert_audit("op", "review_resolve", "review#12", "dismiss")
    fake_db.insert_audit("op", "erase", None, "logs=3 students=1 notifications=0 audit_rows=2")
    return [dict(a) for a in fake_db.audits]


@pytest.mark.parametrize("made_up", ["test", "3", "review%2312", "logs", "dismiss", " "])
def test_erasing_a_made_up_id_cannot_blank_the_audit_log(client, fake_db, made_up):
    before = audit_rows_of_others(fake_db)

    r = client.delete(f"/api/students/{made_up}")

    assert r.status_code == 404
    assert fake_db.audits == before


@pytest.mark.parametrize("sid", ["TEST", "3", "REVIEW#12"])
def test_a_student_whose_id_is_a_common_word_takes_only_their_own_rows(client, fake_db, sid):
    before = audit_rows_of_others(fake_db)
    add(fake_db, sid, "0499AABB")
    fake_db.insert_audit("op", "create", sid, None)

    r = client.delete(f"/api/students/{sid.replace('#', '%23')}")

    assert r.status_code == 200
    assert r.json()["audit_rows"] == 1
    assert fake_db.audits[: len(before)] == before


# --- the real statements ---

DSN = os.environ.get("TEST_DB_DSN", "")


@pytest.mark.skipif(not DSN, reason="TEST_DB_DSN is not set")
def test_after_erase_a_dump_of_every_table_has_no_hit(monkeypatch):
    name = DSN.split("dbname=")[1].split()[0] if "dbname=" in DSN else (
        DSN.rsplit("/", 1)[-1].split("?")[0])
    assert name != "attendance", "TEST_DB_DSN points at the live database"
    monkeypatch.setattr(db, "DB_DSN", DSN)
    db.init_db()
    sid, uid, other_sid, other_uid = "PC044-S1", "PC044AA01", "PC044-S10", "PC044AA0199"

    def dump():
        out = {}
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
                for (table,) in cur.fetchall():
                    cur.execute(f'SELECT row_to_json(t)::text FROM "{table}" t')
                    out[table] = [r[0] for r in cur.fetchall()]
        return out

    def cleanup():
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_logs WHERE uid LIKE 'PC044%'")
                cur.execute("DELETE FROM students WHERE student_id LIKE 'PC044%'")
                cur.execute("DELETE FROM audit_log WHERE actor = 'pc044-test'")

    cleanup()
    try:
        early = db.insert_log(uid=uid, student_id=None, method="nfc", status="unregistered")
        db.insert_student(sid, uid, name="Erased Student",
                          guardian_email="erased@example.com", guardian_mobile="09170000001")
        db.insert_student(other_sid, other_uid, name="Kept Student")
        mine = db.insert_log(uid=uid, student_id=sid, method="nfc", status="flagged")
        theirs = db.insert_log(uid=other_uid, student_id=other_sid, method="nfc",
                               status="accepted")
        db.insert_notification(early["id"], "sms", early["ts"], "DISABLED", "channel off")
        db.insert_notification(mine["id"], "email", mine["ts"])
        kept_note = db.insert_notification(theirs["id"], "email", theirs["ts"])
        db.insert_review(mine["id"], sid, "flagged", f"tailgating; nearest={sid}")
        kept_review = db.insert_review(theirs["id"], other_sid, "flagged",
                                       f"tailgating; nearest={sid}")
        db.insert_audit("pc044-test", "create", sid, f"uid={uid}")
        db.insert_audit("pc044-test", "contact_test", sid, "email test sent")
        db.insert_audit("pc044-test", "enroll", other_sid,
                        f"3 shot(s), buffalo_l; dup?~{sid}@0.912")
        db.insert_audit("pc044-test", "create", other_sid, f"uid={other_uid}")
        db.insert_audit("pc044-test", "contact_test", other_sid, "email test sent")
        db.insert_audit("pc044-test", "review_resolve", "review#999999", "dismiss")
        before = dump()

        # An ID nobody has changes nothing, whatever word it is.
        nothing = {"logs": 0, "students": 0, "notifications": 0, "audit_rows": 0, "uid": None}
        for made_up in ("test", "3", "review#999999", "dismiss", "pc044-s1", ""):
            assert db.delete_student(made_up, "pc044-test") == nothing
        assert dump() == before

        counts = db.delete_student(sid, "pc044-test")

        assert counts == {"logs": 2, "students": 1, "notifications": 2, "audit_rows": 4,
                          "uid": uid}
        tables = dump()
        assert any('"action":"erase","target":null,'
                   '"detail":"logs=2 students=1 notifications=2 audit_rows=4"' in line
                   for line in tables["audit_log"])
        for table, lines in tables.items():
            for line in lines:
                assert sid + '"' not in line and sid + "@" not in line, (table, line)
                assert uid + '"' not in line, (table, line)
                assert "erased@example.com" not in line and "09170000001" not in line
                assert "Erased Student" not in line

        # The student whose ID and UID only start the same is untouched.
        everything = "\n".join(line for lines in tables.values() for line in lines)
        assert other_sid in everything and other_uid in everything
        assert f"uid={other_uid}" in everything
        assert any(n["id"] == kept_note["id"] for n in db.get_notifications())
        assert any(f'"id":{kept_review["id"]},' in line and '"reason":null' in line
                   for line in tables["review_queue"])
        assert "email test sent" in everything and '"detail":"dismiss"' in everything
        assert db.delete_student(sid, "pc044-test") == nothing
    finally:
        cleanup()
