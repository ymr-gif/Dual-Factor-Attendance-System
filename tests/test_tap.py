"""Smoke tests for `POST /tap` and `GET /health`, driven through FastAPI's TestClient.

No Postgres, camera, model file or network is used: see `conftest.py` for the fakes.
`/tap` has two modes, chosen by `PERCEPTION_ENABLED`:

- off (the code default): the request captures one probe from the camera, checks
  face and liveness, and writes the verdict before it answers;
- on (what the installer's `.env` and service units set): the request only queues
  the tap, and the matcher writes the verdict after its association window.
"""

import pytest

from backend import decision

UID = "C3BE343A"
EMBEDDING = [0.1, 0.2, 0.3]


def enrolled_student(**overrides):
    row = {
        "student_id": "S001",
        "uid": UID,
        "name": "Test Student",
        "guardian_email": "guardian@example.com",
        "face_embedding": EMBEDDING,
        "embed_model": "buffalo_l",
        "face_consent": False,
    }
    row.update(overrides)
    return row


def post_tap(client, uid=UID, **extra):
    return client.post("/tap", json={"uid": uid, **extra})


# --- /health ---------------------------------------------------------------


def test_startup_runs_the_schema_migration_once(client, fake_db):
    assert fake_db.init_calls == 1


def test_health_ok_when_database_answers(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True}


def test_health_degraded_but_still_200_when_database_is_down(client, fake_db):
    fake_db.reachable = False
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "db": False}


# --- /tap, perception off: verdict in the response ---------------------------


def test_unknown_card_is_logged_as_unregistered(client, fake_db, camera, sinks):
    response = post_tap(client, uid="DEADBEEF")

    assert response.status_code == 200
    body = response.json()
    assert body["student"] is None
    assert body["log"]["status"] == decision.UNREGISTERED
    assert body["log"]["uid"] == "DEADBEEF"
    assert body["log"]["student_id"] is None

    assert len(fake_db.logs) == 1
    assert camera.captures == 0, "no face check is attempted for an unknown card"
    assert sinks.notified == [(None, fake_db.logs[0])]


def test_known_card_returns_the_student_without_the_face_embedding(client, fake_db, sinks):
    fake_db.add_student(enrolled_student())

    body = post_tap(client).json()

    assert "face_embedding" not in body["student"]
    assert body["student"] == {
        "student_id": "S001",
        "uid": UID,
        "name": "Test Student",
        "guardian_email": "guardian@example.com",
        "embed_model": "buffalo_l",
        "face_consent": False,
    }
    assert body["log"]["student_id"] == "S001"

    # The WebSocket event must not carry it either.
    assert len(sinks.published) == 1
    event = sinks.published[0]
    assert event["type"] == "tap"
    assert "face_embedding" not in event["student"]
    assert EMBEDDING not in event["student"].values()


@pytest.mark.parametrize("raw", ["c3be343a", "  C3BE343A  ", "\tc3Be343A\n"])
def test_uid_is_stripped_and_uppercased_before_lookup(client, fake_db, raw):
    fake_db.add_student(enrolled_student())

    body = post_tap(client, uid=raw).json()

    assert fake_db.lookups == [UID]
    assert body["student"]["student_id"] == "S001"
    assert fake_db.logs[0]["uid"] == UID


def test_no_usable_face_fails_open_as_unverified(client, fake_db, camera):
    fake_db.add_student(enrolled_student())

    body = post_tap(client).json()

    assert camera.captures == 1
    assert body["log"]["status"] == decision.UNVERIFIED
    assert body["log"]["face_score"] is None
    assert body["log"]["face_match"] is None
    assert body["log"]["liveness_score"] is None
    assert body["log"]["liveness_pass"] is None


def test_matching_live_face_is_accepted(client, fake_db, camera):
    fake_db.add_student(enrolled_student())
    camera.sees(score=0.86, live_score=0.97, is_live=True)

    log = post_tap(client).json()["log"]

    assert log["status"] == decision.ACCEPTED
    assert log["face_score"] == 0.86
    assert log["face_match"] is True
    assert log["liveness_score"] == 0.97
    assert log["liveness_pass"] is True
    assert log["method"] == "nfc"


@pytest.mark.parametrize(
    ("score", "is_live"),
    [(0.018, True), (0.86, False)],
    ids=["face-mismatch", "liveness-fail"],
)
def test_failed_factor_is_flagged_by_default_and_rejected_when_enforcing(
    client, fake_db, camera, monkeypatch, score, is_live
):
    fake_db.add_student(enrolled_student())
    camera.sees(score=score, live_score=0.5, is_live=is_live)

    assert post_tap(client).json()["log"]["status"] == decision.FLAGGED

    monkeypatch.setattr(decision, "ENFORCE_2FA", True)
    assert post_tap(client).json()["log"]["status"] == decision.REJECTED

    # Rejected taps are still stored for audit.
    assert [row["status"] for row in fake_db.logs] == [decision.FLAGGED, decision.REJECTED]


def test_score_exactly_at_threshold_is_a_match(client, fake_db, camera):
    fake_db.add_student(enrolled_student())
    camera.sees(score=0.5, live_score=0.9, is_live=True)

    log = post_tap(client).json()["log"]

    assert log["face_match"] is True
    assert log["status"] == decision.ACCEPTED


def test_student_without_reference_skips_face_match_but_still_checks_liveness(
    client, fake_db, camera
):
    fake_db.add_student(enrolled_student(face_embedding=None))
    camera.sees(score=0.86, live_score=0.9, is_live=True)

    log = post_tap(client).json()["log"]

    assert log["face_score"] is None
    assert log["face_match"] is None
    assert log["liveness_pass"] is True
    assert log["status"] == decision.ACCEPTED


def test_consent_gate_skips_the_camera_for_an_unconsented_student(
    client, fake_db, camera, monkeypatch
):
    from backend import privacy

    fake_db.add_student(enrolled_student(face_consent=False))
    camera.sees(score=0.86, live_score=0.9, is_live=True)
    monkeypatch.setattr(privacy, "FACE_CONSENT_REQUIRED", True)

    log = post_tap(client).json()["log"]

    assert camera.captures == 0
    assert log["status"] == decision.UNVERIFIED


def test_face_and_liveness_both_disabled_never_opens_the_camera(
    client, fake_db, camera, monkeypatch
):
    from backend import face, liveness

    fake_db.add_student(enrolled_student())
    monkeypatch.setattr(face, "FACE_MATCH_ENABLED", False)
    monkeypatch.setattr(liveness, "LIVENESS_ENABLED", False)

    log = post_tap(client).json()["log"]

    assert camera.captures == 0
    assert log["status"] == decision.UNVERIFIED


def test_notify_failure_does_not_fail_the_tap(client, fake_db, sinks):
    fake_db.add_student(enrolled_student())
    sinks.notify_error = RuntimeError("smtp is down (simulated)")

    response = post_tap(client)

    assert response.status_code == 200
    assert len(fake_db.logs) == 1
    assert len(sinks.published) == 1, "the live event is still broadcast"


def test_method_defaults_to_nfc_and_can_be_overridden(client, fake_db):
    post_tap(client, uid="AAAA0001")
    post_tap(client, uid="AAAA0002", method="manual")
    assert [row["method"] for row in fake_db.logs] == ["nfc", "manual"]


def test_missing_uid_is_a_validation_error_and_logs_nothing(client, fake_db):
    response = client.post("/tap", json={})
    assert response.status_code == 422
    assert fake_db.logs == []


# --- /tap, perception on: verdict deferred to the matcher --------------------


@pytest.fixture
def perception_on(client, monkeypatch):
    from backend import perception

    monkeypatch.setattr(perception, "PERCEPTION_ENABLED", True)
    return client


def test_perception_unknown_card_is_logged_at_once(perception_on, fake_db, fake_matcher):
    body = post_tap(perception_on, uid="deadbeef").json()

    assert body["status"] == "logged"
    assert body["student"] is None
    assert body["log"]["status"] == decision.UNREGISTERED
    assert body["log"]["uid"] == "DEADBEEF"
    assert fake_matcher.taps == []


def test_perception_enrolled_card_is_queued_not_logged(
    perception_on, fake_db, fake_matcher, camera
):
    student = fake_db.add_student(enrolled_student())

    body = post_tap(perception_on, uid=" c3be343a ").json()

    assert body == {
        "status": "queued",
        "uid": UID,
        "student": {k: v for k, v in student.items() if k != "face_embedding"},
    }
    assert fake_matcher.taps == [
        {"uid": UID, "student_id": "S001", "embedding": EMBEDDING, "student": student}
    ]
    assert fake_db.logs == [], "the matcher writes the log later, not the request"
    assert camera.captures == 0, "perception owns the camera; /tap must not open it"


def test_perception_repeat_tap_inside_cooldown_is_debounced(perception_on, fake_db, fake_matcher):
    fake_db.add_student(enrolled_student())
    fake_matcher.debounce = True

    body = post_tap(perception_on).json()

    assert body["status"] == "debounced"
    assert "face_embedding" not in body["student"]
    assert fake_db.logs == []


def test_perception_student_without_reference_is_logged_unverified(
    perception_on, fake_db, fake_matcher
):
    fake_db.add_student(enrolled_student(face_embedding=None))

    body = post_tap(perception_on).json()

    assert body["status"] == "logged"
    assert body["log"]["status"] == decision.UNVERIFIED
    assert fake_matcher.taps == []


def test_perception_consent_gate_logs_card_only(perception_on, fake_db, fake_matcher, monkeypatch):
    from backend import privacy

    fake_db.add_student(enrolled_student(face_consent=False))
    monkeypatch.setattr(privacy, "FACE_CONSENT_REQUIRED", True)

    body = post_tap(perception_on).json()

    assert body["status"] == "logged"
    assert body["log"]["status"] == decision.UNVERIFIED
    assert fake_matcher.taps == []


# --- operator token -----------------------------------------------------------


def test_api_is_open_when_operator_token_is_unset(client, fake_db):
    fake_db.add_student(enrolled_student())

    response = client.get("/api/students")

    assert response.status_code == 200
    assert [s["student_id"] for s in response.json()["students"]] == ["S001"]


def test_operator_token_guards_api_but_not_tap_or_health(client, fake_db, backend_main, monkeypatch):
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "s3cret")

    assert client.get("/api/students").status_code == 401
    assert client.get("/api/students", headers={"X-Operator-Token": "wrong"}).status_code == 401
    assert client.get("/api/students", headers={"X-Operator-Token": "s3cret"}).status_code == 200
    assert client.get("/api/students", headers={"Authorization": "Bearer s3cret"}).status_code == 200

    # The serial reader posts taps without a token, so /tap stays open.
    assert post_tap(client, uid="DEADBEEF").status_code == 200
    assert client.get("/health").status_code == 200
