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


# --- review queue: a tap that failed a check is put in front of an operator ----------


def test_flagged_tap_is_queued_for_review_with_the_reason(client, fake_db, camera):
    fake_db.add_student(enrolled_student())
    camera.sees(score=0.018, live_score=0.1, is_live=False)

    log = post_tap(client).json()["log"]

    assert log["status"] == decision.FLAGGED
    assert fake_db.reviews == [
        {
            "log_id": log["id"],
            "student_id": "S001",
            "status": decision.FLAGGED,
            "reason": "face below match threshold; liveness fail",
        }
    ]


def test_rejected_tap_is_queued_for_review(client, fake_db, camera, monkeypatch):
    monkeypatch.setattr(decision, "ENFORCE_2FA", True)
    fake_db.add_student(enrolled_student())
    camera.sees(score=0.86, live_score=0.1, is_live=False)

    log = post_tap(client).json()["log"]

    assert log["status"] == decision.REJECTED
    assert [(r["log_id"], r["status"], r["reason"]) for r in fake_db.reviews] == [
        (log["id"], decision.REJECTED, "liveness fail")
    ]


def test_taps_that_passed_or_could_not_be_checked_are_not_queued(client, fake_db, camera):
    fake_db.add_student(enrolled_student())

    post_tap(client)  # no usable face -> unverified
    camera.sees(score=0.86, live_score=0.97, is_live=True)
    post_tap(client)  # accepted
    post_tap(client, uid="DEADBEEF")  # unregistered

    assert [row["status"] for row in fake_db.logs] == [
        decision.UNVERIFIED,
        decision.ACCEPTED,
        decision.UNREGISTERED,
    ]
    assert fake_db.reviews == []


def test_review_queue_failure_does_not_fail_the_tap(client, fake_db, camera, sinks):
    fake_db.review_error = RuntimeError("review_queue is unavailable")
    fake_db.add_student(enrolled_student())
    camera.sees(score=0.018, live_score=0.97, is_live=True)

    response = post_tap(client)

    assert response.status_code == 200
    assert response.json()["log"]["status"] == decision.FLAGGED
    assert len(sinks.notified) == 1 and len(sinks.published) == 1


def matcher_outcome(status, **extra):
    """An outcome dict the way backend.matcher builds one."""
    outcome = {
        "status": status,
        "uid": UID,
        "student_id": "S001",
        "student": enrolled_student(),
        "method": "nfc+face",
        "face_score": None,
        "face_match": None,
        "liveness_score": None,
        "liveness_pass": None,
        "track_id": None,
        "reason": None,
        "camera_down": False,
    }
    outcome.update(extra)
    return outcome


@pytest.mark.parametrize(
    "status",
    [decision.NO_FACE, decision.MISMATCH, decision.SPOOF, decision.TAILGATING],
)
def test_matcher_review_states_are_logged_and_queued(client, backend_main, fake_db, sinks, status):
    backend_main._write_outcome(matcher_outcome(status, reason="why the matcher said so"))

    assert [row["status"] for row in fake_db.logs] == [status]
    assert fake_db.reviews == [
        {"log_id": 1, "student_id": "S001", "status": status, "reason": "why the matcher said so"}
    ]
    assert sinks.published[0]["reason"] == "why the matcher said so"
    assert "face_embedding" not in sinks.published[0]["student"]


@pytest.mark.parametrize("status", [decision.ACCEPTED, decision.UNVERIFIED])
def test_matcher_outcomes_that_count_are_logged_but_not_queued(
    client, backend_main, fake_db, sinks, status
):
    backend_main._write_outcome(matcher_outcome(status, reason="verified"))

    assert [row["status"] for row in fake_db.logs] == [status]
    assert fake_db.reviews == []
    assert len(sinks.notified) == 1


def test_matcher_outcome_survives_a_review_queue_failure(client, backend_main, fake_db, sinks):
    fake_db.review_error = RuntimeError("review_queue is unavailable")

    backend_main._write_outcome(matcher_outcome(decision.MISMATCH, reason="below threshold"))

    assert [row["status"] for row in fake_db.logs] == [decision.MISMATCH]
    assert len(sinks.notified) == 1 and len(sinks.published) == 1


# --- camera heartbeat: what lets the matcher tell `no_face` from an unwatched tap -----


def test_a_tap_the_camera_never_watched_is_reviewed_although_it_counts(
    client, backend_main, fake_db, sinks, capsys
):
    outcome = matcher_outcome(
        decision.UNVERIFIED,
        method="nfc",
        reason="camera delivered no frame during the tap; card-only",
        camera_down=True,
    )

    backend_main._write_outcome(outcome)

    assert [row["status"] for row in fake_db.logs] == [decision.UNVERIFIED]
    # `unverified` alone is never queued; this one is, so the outage cannot pass unseen.
    assert fake_db.reviews == [
        {
            "log_id": 1,
            "student_id": "S001",
            "status": decision.UNVERIFIED,
            "reason": "camera delivered no frame during the tap; card-only",
        }
    ]
    assert "[ALERT] camera delivered no frame" in capsys.readouterr().out
    assert len(sinks.notified) == 1 and len(sinks.published) == 1


def test_the_app_matcher_listens_for_the_camera_heartbeat(backend_main):
    from backend import matcher as matcher_mod

    # `backend_main.matcher` is swapped for a fake by the `client` fixture, so find the
    # real instance by type.
    app_matcher = [
        value for value in vars(backend_main).values() if isinstance(value, matcher_mod.Matcher)
    ]
    assert app_matcher, "backend.main no longer builds a Matcher at import"
    assert app_matcher[0].camera_heartbeat is True


def test_frame_sink_forwards_the_frame_time_to_the_matcher(backend_main, monkeypatch):
    seen = []

    class Recorder:
        def note_frame(self, ts=None):
            seen.append(ts)

    monkeypatch.setattr(backend_main, "matcher", Recorder())

    backend_main._note_frame("frame", {"ts": 1234.5, "tracks": []})

    assert seen == [1234.5]


def test_startup_registers_the_heartbeat_with_perception(backend_main, monkeypatch):
    import asyncio

    from backend import perception

    registered = []
    monkeypatch.setattr(perception, "PERCEPTION_ENABLED", True)
    monkeypatch.setattr(perception, "on_frame", registered.append)
    monkeypatch.setattr(perception, "on_face", lambda cb: None)
    monkeypatch.setattr(perception, "run", lambda *a, **k: None)
    monkeypatch.setattr(perception, "_camera_frames", lambda: iter(()))

    async def start():
        await backend_main._start_perception()
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()  # the matcher resolve loop the hook starts

    asyncio.run(start())

    assert backend_main._note_frame in registered


# --- /stream.mjpeg: the live camera image is locked with the rest of the API ---------


@pytest.fixture
def locked(backend_main, monkeypatch):
    """OPERATOR_TOKEN set, no tickets outstanding."""
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "s3cret")
    monkeypatch.setattr(backend_main, "_stream_tickets", {})
    return backend_main


def test_stream_is_refused_without_a_ticket_or_token(client, locked, monkeypatch):
    from fastapi.responses import PlainTextResponse

    # The real response never ends. If the guard were ever removed, this stand-in turns
    # what would be a hung test run into a plain 200 and a failed assertion.
    monkeypatch.setattr(locked, "StreamingResponse", lambda *a, **k: PlainTextResponse("frames"))

    assert client.get("/stream.mjpeg").status_code == 401
    assert client.get("/stream.mjpeg?ticket=made-up").status_code == 401
    assert client.get("/stream.mjpeg", headers={"X-Operator-Token": "wrong"}).status_code == 401


def test_the_operator_token_is_not_accepted_from_the_url(client, locked, monkeypatch):
    from fastapi.responses import PlainTextResponse

    monkeypatch.setattr(locked, "StreamingResponse", lambda *a, **k: PlainTextResponse("frames"))

    # A token in a URL ends up in access logs and browser history.
    assert client.get("/stream.mjpeg?token=s3cret").status_code == 401
    assert client.get("/stream.mjpeg?ticket=s3cret").status_code == 401


def test_a_ticket_is_only_issued_to_a_caller_with_the_token(client, locked):
    assert client.post("/api/stream-ticket").status_code == 401
    assert locked._stream_tickets == {}

    response = client.post("/api/stream-ticket", headers={"X-Operator-Token": "s3cret"})

    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 60
    assert body["ticket"] != "s3cret" and len(body["ticket"]) >= 32
    assert list(locked._stream_tickets) == [body["ticket"]]


def test_an_issued_ticket_opens_the_stream_and_the_token_header_still_works(client, locked, monkeypatch):
    from fastapi.responses import PlainTextResponse

    monkeypatch.setattr(locked, "StreamingResponse", lambda *a, **k: PlainTextResponse("frames"))
    ticket = client.post("/api/stream-ticket", headers={"X-Operator-Token": "s3cret"}).json()["ticket"]

    assert client.get(f"/stream.mjpeg?ticket={ticket}").status_code == 200
    assert client.get("/stream.mjpeg", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_a_ticket_stops_working_when_it_expires(locked, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(locked.time, "monotonic", lambda: clock["now"])
    guard = locked.require_stream_access
    ticket = locked._issue_stream_ticket()

    assert guard(ticket=ticket, authorization=None, x_operator_token=None) is None

    clock["now"] += locked.STREAM_TICKET_TTL  # exactly at expiry: no longer valid
    with pytest.raises(Exception) as denied:
        guard(ticket=ticket, authorization=None, x_operator_token=None)
    assert getattr(denied.value, "status_code", None) == 401


def test_a_bad_ticket_is_not_rescued_by_a_valid_header(locked):
    # Otherwise "?ticket=anything" plus a stolen page would behave differently from
    # no ticket at all; one credential, one verdict.
    with pytest.raises(Exception) as denied:
        locked.require_stream_access(ticket="made-up", authorization="Bearer s3cret", x_operator_token=None)
    assert getattr(denied.value, "status_code", None) == 401


def test_expired_tickets_are_dropped_and_the_store_is_bounded(locked, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(locked.time, "monotonic", lambda: clock["now"])

    old = locked._issue_stream_ticket()
    clock["now"] = locked.STREAM_TICKET_TTL + 1
    fresh = locked._issue_stream_ticket()
    assert old not in locked._stream_tickets and fresh in locked._stream_tickets

    for _ in range(locked._STREAM_TICKET_LIMIT + 50):
        locked._issue_stream_ticket()
    assert len(locked._stream_tickets) <= locked._STREAM_TICKET_LIMIT


def test_stream_is_open_when_no_token_is_configured(backend_main, monkeypatch):
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "")
    guard = backend_main.require_stream_access

    assert guard(ticket=None, authorization=None, x_operator_token=None) is None
    assert guard(ticket="anything", authorization=None, x_operator_token=None) is None


def test_stream_route_carries_the_guard(backend_main):
    route = next(r for r in backend_main.app.routes if getattr(r, "path", "") == "/stream.mjpeg")

    assert backend_main.require_stream_access in [d.call for d in route.dependant.dependencies]
