"""A face with no tap (PC-031). The system searches no enrolled faces and names
nobody; the guard sees the alert, picks the student from the roster or dismisses it,
and the review row keeps who picked whom and when. The audit row keeps the
resolution word only.
"""

import pytest

from backend import decision
from backend import matcher as matcher_mod

STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student",
           "guardian_email": None, "guardian_mobile": None, "face_embedding": None}


# --- the matcher ---


def untapped_face(face_search):
    emitted = []
    m = matcher_mod.Matcher(window=4.0, cooldown=2.0, threshold=0.5, tailgate_threshold=0.5,
                            outcome_sink=emitted.append, face_search=face_search,
                            clock=lambda: 0.0)
    m.on_face({"track_id": 1, "embedding": [0.1, 0.2, 0.3], "is_live": True, "ts": 0.0})
    m.resolve(now=10.0)
    (outcome,) = emitted
    return outcome


def test_a_face_with_no_tap_is_flagged_and_named_by_nobody():
    o = untapped_face(face_search=None)

    assert o["status"] == decision.TAILGATING
    assert o["student_id"] is None and o["student"] is None
    assert o["face_score"] is None
    assert o["reason"] == "face with no tap"


def test_the_lookup_runs_only_when_it_is_switched_on():
    calls = []

    def search(embedding, k):
        calls.append(k)
        return [{"student_id": "S001", "similarity": 0.9}]

    o = untapped_face(face_search=search)

    assert calls == [1]
    assert o["student_id"] == "S001"
    assert o["reason"] == "tailgating; nearest=S001"


def test_the_backend_builds_its_matcher_without_the_lookup(backend_main):
    assert backend_main.FACE_SEARCH_ENABLED is False
    assert backend_main.matcher.face_search is None


def test_the_face_lookup_page_is_closed(client):
    response = client.post("/api/search-face", files={"image": ("f.jpg", b"x", "image/jpeg")})

    assert response.status_code == 403


# --- the guard resolves it ---


@pytest.fixture
def alert(client, backend_main, fake_db):
    fake_db.add_student(STUDENT)
    outcome = untapped_face(face_search=None)
    backend_main._write_outcome(outcome)
    (review,) = fake_db.reviews
    assert review["status"] == decision.TAILGATING and review["student_id"] is None
    return 1


def resolve(client, review_id, **body):
    return client.post(f"/api/review/{review_id}/resolve", json=body)


def test_the_guard_picks_the_student_from_the_roster(client, fake_db, alert):
    response = resolve(client, alert, resolution="identified", student_id="s001")

    assert response.status_code == 200
    assert response.json()["identified_as"] == "S001"
    stored = fake_db.resolutions[alert]
    assert (stored["resolution"], stored["identified_as"]) == ("identified", "S001")
    assert stored["resolved_by"]  # who; the database stamps when


def test_the_audit_row_holds_the_word_and_not_the_student(client, fake_db, alert):
    resolve(client, alert, resolution="identified", student_id="S001")

    (row,) = [a for a in fake_db.audits if a["action"] == "review_resolve"]
    assert (row["target"], row["detail"]) == (f"review#{alert}", "identified")


def test_the_guard_can_dismiss_it(client, fake_db, alert):
    response = resolve(client, alert, resolution="dismiss", student_id="S001")

    assert response.status_code == 200
    assert fake_db.resolutions[alert]["identified_as"] is None


@pytest.mark.parametrize("student_id", [None, "", "S999"])
def test_a_pick_that_is_not_on_the_roster_is_refused(client, fake_db, alert, student_id):
    response = resolve(client, alert, resolution="identified", student_id=student_id)

    assert response.status_code == 422
    assert alert not in fake_db.resolutions


def test_only_a_face_with_no_tap_can_be_identified(client, backend_main, fake_db):
    fake_db.add_student(STUDENT)
    backend_main._write_outcome({"status": decision.MISMATCH, "uid": "C3BE343A",
                                 "student_id": "S001", "student": STUDENT, "method": "nfc+face"})

    response = resolve(client, 1, resolution="identified", student_id="S001")

    assert response.status_code == 404
    assert fake_db.resolutions == {}


def test_an_erase_takes_the_pick_with_it(client, fake_db, alert):
    resolve(client, alert, resolution="identified", student_id="S001")

    assert client.delete("/api/students/S001").status_code == 200

    assert fake_db.resolutions[alert]["identified_as"] is None
