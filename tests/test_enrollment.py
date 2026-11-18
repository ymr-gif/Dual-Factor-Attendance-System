"""Enrollment stays out of the attendance data (18 Nov, Cabucos).

A card tapped to fill a UID on Register or Roster is handed to that page and not
logged. While the Register page is open, a face with no tap is not flagged. A student
accepted moments ago who stays in view is not flagged either. The guardian step of a
scan says what really happened to the message.
"""

import pytest

from backend import decision, enrollment
from backend import matcher as matcher_mod

UID = "C3BE343A"


@pytest.fixture(autouse=True)
def reset():
    enrollment.disarm_card()
    enrollment.stop_enrolling()
    yield
    enrollment.disarm_card()
    enrollment.stop_enrolling()


def student(uid=UID, sid="S001", email="g@example.com"):
    return {"student_id": sid, "uid": uid, "name": "Test Student", "guardian_email": email,
            "guardian_mobile": None, "face_embedding": [0.1, 0.2, 0.3],
            "embed_model": "buffalo_l", "face_consent": False}


# --- card capture ---

def test_an_armed_card_read_goes_to_the_page_and_is_not_logged(client, fake_db, sinks):
    assert client.post("/api/enroll/card", json={"seconds": 20}).status_code == 200

    body = client.post("/tap", json={"uid": "d4cf454b"}).json()

    assert body == {"status": "captured", "uid": "D4CF454B"}
    assert fake_db.logs == [] and fake_db.reviews == [] and sinks.notified == []
    assert sinks.published[-1] == {"type": "card_capture", "uid": "D4CF454B", "student_id": None}
    assert sinks.stages == []  # no scan animation for an enrollment read


def test_an_enrolled_card_read_for_enrollment_names_its_owner_and_is_not_logged(client, fake_db, sinks):
    fake_db.add_student(student())
    client.post("/api/enroll/card", json={})

    client.post("/tap", json={"uid": UID})

    assert fake_db.logs == []
    assert sinks.published[-1]["student_id"] == "S001"


def test_one_arm_takes_one_card_and_the_next_tap_is_attendance(client, fake_db, sinks):
    client.post("/api/enroll/card", json={})
    client.post("/tap", json={"uid": "D4CF454B"})

    client.post("/tap", json={"uid": "D4CF454B"})

    assert [log["status"] for log in fake_db.logs] == [decision.UNREGISTERED]


def test_a_cancelled_arm_logs_the_tap(client, fake_db):
    client.post("/api/enroll/card", json={})
    client.delete("/api/enroll/card")

    client.post("/tap", json={"uid": "D4CF454B"})

    assert len(fake_db.logs) == 1


def test_a_capture_is_audited_without_the_card_uid(client, fake_db):
    fake_db.add_student(student())
    client.post("/api/enroll/card", json={})

    client.post("/tap", json={"uid": UID})

    caps = [a for a in fake_db.audits if a["action"] == "card_capture"]
    assert [a["target"] for a in caps] == ["S001"]
    assert UID not in str(fake_db.audits)


def test_a_lost_card_is_not_captured_and_is_still_logged_revoked(client, fake_db, sinks):
    fake_db.add_student(student())
    client.post("/api/students/S001/card/lost")
    client.post("/api/enroll/card", json={})

    body = client.post("/tap", json={"uid": UID}).json()

    assert body["status"] != "captured"
    assert [log["status"] for log in fake_db.logs] == [decision.REVOKED]
    assert enrollment.armed()  # the arm still waits for the new card


def test_an_enrollment_session_has_a_hard_limit():
    assert enrollment.keep_enrolling(now=0.0)
    t = 0.0
    while t < enrollment.ENROLLING_MAX_SEC - 4:
        t += 4
        enrollment.keep_enrolling(now=t)
    assert not enrollment.keep_enrolling(now=enrollment.ENROLLING_MAX_SEC)
    assert not enrollment.active(now=enrollment.ENROLLING_MAX_SEC + 1)


def test_a_reopened_register_page_starts_a_new_session():
    enrollment.keep_enrolling(now=0.0)
    enrollment.keep_enrolling(now=enrollment.ENROLLING_MAX_SEC + 1)  # gap: page was closed
    assert enrollment.active(now=enrollment.ENROLLING_MAX_SEC + 2)


def test_turning_enrollment_on_and_off_is_audited(client, fake_db):
    client.post("/api/enroll/active")
    client.post("/api/enroll/active")
    client.delete("/api/enroll/active")

    assert [a["action"] for a in fake_db.audits] == ["enroll_mode_on", "enroll_mode_off"]


def test_an_arm_ends_by_itself():
    enrollment.arm_card(20, now=100.0)
    assert not enrollment.take_card(now=121.0)


def test_an_arm_is_capped():
    assert enrollment.arm_card(3600, now=0.0) == enrollment.CARD_CAPTURE_MAX_SEC


# --- enrolling at the camera ---

def test_enrolling_ends_by_itself_after_the_page_stops_calling():
    enrollment.keep_enrolling(now=100.0)
    assert enrollment.active(now=105.0)
    assert not enrollment.active(now=100.0 + enrollment.ENROLLING_SEC + 0.1)


def test_the_register_heartbeat_turns_enrolling_on_and_off(client):
    assert client.post("/api/enroll/active").status_code == 200
    assert enrollment.active()
    client.delete("/api/enroll/active")
    assert not enrollment.active()


def build():
    return matcher_mod.Matcher(window=4.0, cooldown=2.0, threshold=0.5, tailgate_threshold=0.5,
                               outcome_sink=None, face_search=None, clock=lambda: 0.0)


def unit(i, n=8):
    v = [0.0] * n
    v[i] = 1.0
    return v


def blend(a, b, w):
    """A face between two others: cosine to `a` is about cos(w * 90 degrees)."""
    import math
    return [math.cos(w * math.pi / 2) * x + math.sin(w * math.pi / 2) * y for x, y in zip(a, b)]


def test_a_face_with_no_tap_is_not_flagged_while_enrolling():
    m = build()
    enrollment.keep_enrolling()
    m.on_face({"track_id": 1, "embedding": unit(0), "is_live": True, "ts": 0.0})

    assert m.resolve(now=5.0) == []


def test_a_face_with_no_tap_is_flagged_again_after_enrolling():
    m = build()
    m.on_face({"track_id": 1, "embedding": unit(0), "is_live": True, "ts": 0.0})

    assert [o["status"] for o in m.resolve(now=5.0)] == [decision.TAILGATING]


# --- a student accepted moments ago, still in view ---

def accepted_then(monkeypatch, later_face, later_at=20.0):
    """Student with enrolled face unit(0) taps and is accepted on a first view that is
    far from the enrolled face's later views; then `later_face` shows on a new track."""
    m = build()
    monkeypatch.setattr(m, "_assign", lambda taps, faces: {0: 0} if faces else {})
    monkeypatch.setattr(matcher_mod.face, "cosine", lambda a, b: 0.8)
    m.on_face({"track_id": 1, "embedding": blend(unit(0), unit(1), 0.6), "is_live": True, "ts": 0.0})
    m.add_tap(UID, "S001", unit(0), student=student(), ts=0.5)
    first = m.resolve(now=5.0)
    m.on_face({"track_id": 2, "embedding": later_face, "is_live": True, "ts": later_at})
    return first, m.resolve(now=later_at + 5.0)


def test_an_accepted_student_still_in_view_on_a_new_track_is_not_flagged(monkeypatch):
    # Close to the enrolled face (0.71), far from the first view (below 0.6).
    first, later = accepted_then(monkeypatch, blend(unit(0), unit(2), 0.5))

    assert [o["status"] for o in first] == [decision.ACCEPTED]
    assert later == []


def test_someone_else_after_an_accepted_tap_is_still_flagged(monkeypatch):
    _, later = accepted_then(monkeypatch, unit(3))

    assert [o["status"] for o in later] == [decision.TAILGATING]


def test_the_accepted_student_is_forgotten_after_the_dwell_gap(monkeypatch):
    _, later = accepted_then(monkeypatch, blend(unit(0), unit(2), 0.5), later_at=120.0)

    assert [o["status"] for o in later] == [decision.TAILGATING]


# --- the guardian step of a scan ---

def test_the_guardian_step_says_no_email_on_file(backend_main, monkeypatch):
    monkeypatch.setattr(backend_main.notify_mod, "EMAIL_ENABLED", True)
    monkeypatch.setattr(backend_main.notify_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(backend_main.notify_mod, "SMS_ENABLED", False)
    log = {"status": decision.ACCEPTED, "student_id": "S001"}

    text, done = backend_main._notify_step(log, student(email=None))

    assert done and text == "no guardian message (no guardian email on file, SMS off)"


def test_the_guardian_step_stays_open_while_the_email_is_sent(backend_main, monkeypatch):
    monkeypatch.setattr(backend_main.notify_mod, "EMAIL_ENABLED", True)
    monkeypatch.setattr(backend_main.notify_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(backend_main.notify_mod, "SMS_ENABLED", False)
    log = {"status": decision.ACCEPTED, "student_id": "S001"}

    assert backend_main._notify_step(log, student()) == ("sending guardian email", False)


def test_the_sent_email_closes_the_guardian_step(monkeypatch):
    from datetime import datetime, timezone

    from backend import notify

    steps = []
    monkeypatch.setattr(notify.livelog, "stage", lambda uid, step, text, done=False: steps.append((uid, step, text, done)))
    monkeypatch.setitem(notify._SENDERS, "email", lambda s, log, timeout: None)
    log = {"id": 1, "uid": UID, "ts": datetime.now(timezone.utc)}

    notify._job("email", student(), log)(10)

    assert steps[-1][:2] == (UID, "notify") and steps[-1][3] is True
    assert steps[-1][2].startswith("guardian email sent in ")


def test_a_failed_email_closes_the_guardian_step_with_the_reason(monkeypatch):
    from datetime import datetime, timezone

    from backend import notify

    steps = []

    def refuse(s, log, timeout):
        raise PermissionError("refused")

    monkeypatch.setattr(notify.livelog, "stage", lambda uid, step, text, done=False: steps.append((text, done)))
    monkeypatch.setitem(notify._SENDERS, "email", refuse)

    with pytest.raises(PermissionError):
        notify._job("email", student(), {"id": 1, "uid": UID, "ts": datetime.now(timezone.utc)})(10)

    assert steps[-1] == ("guardian email not sent (PermissionError)", True)
