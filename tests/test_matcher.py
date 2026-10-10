"""The matcher's verdict for a tap that no face claimed.

`no_face` means the camera was watching and nobody showed their face. It does not
count as present. A tap the camera never watched cannot be called that, so it comes
out `unverified` (card-only, flagged for review) instead. What decides between the
two is whether any camera frame fell inside the tap's own association window.

These tests drive `Matcher` with explicit timestamps; no camera, model or database.
"""

import pytest

from backend import decision
from backend import matcher as matcher_mod

WINDOW = 4.0
STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student"}


def build(camera_heartbeat=True):
    emitted = []
    m = matcher_mod.Matcher(
        window=WINDOW,
        cooldown=2.0,
        threshold=0.5,
        tailgate_threshold=0.5,
        outcome_sink=emitted.append,
        face_search=None,
        clock=lambda: 0.0,
        camera_heartbeat=camera_heartbeat,
    )
    return m, emitted


def tap(m, at=0.0):
    return m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=at)


def statuses(outcomes):
    return [o["status"] for o in outcomes]


def test_without_a_heartbeat_an_unclaimed_tap_is_no_face():
    # Tests and offline runs feed no frames; a missing frame then proves nothing.
    m, emitted = build(camera_heartbeat=False)
    tap(m)

    outcomes = m.resolve(now=WINDOW)

    assert statuses(outcomes) == [decision.NO_FACE]
    assert outcomes[0]["reason"] == "no face in association window"
    assert outcomes[0]["camera_down"] is False
    assert emitted == outcomes


def test_tap_the_camera_watched_is_no_face():
    m, _ = build()
    tap(m, at=0.0)
    m.note_frame(ts=1.0)

    outcomes = m.resolve(now=WINDOW)

    assert statuses(outcomes) == [decision.NO_FACE]
    assert outcomes[0]["camera_down"] is False


def test_tap_the_camera_never_watched_is_unverified_and_marked_for_review():
    m, emitted = build()
    tap(m)

    outcomes = m.resolve(now=WINDOW)

    assert statuses(outcomes) == [decision.UNVERIFIED]
    assert outcomes[0]["reason"] == "camera delivered no frame during the tap; card-only"
    assert outcomes[0]["camera_down"] is True
    assert outcomes[0]["student_id"] == "S001"
    assert outcomes[0]["face_match"] is None and outcomes[0]["liveness_pass"] is None
    assert emitted == outcomes


def test_a_frame_just_before_the_tap_counts_as_watching():
    # The window reaches back (face-then-tap), so the camera was up for this tap even
    # if it died the moment the card was read. Strict verdict: no_face, not counted.
    m, _ = build()
    m.note_frame(ts=-1.0)
    tap(m, at=0.0)

    assert statuses(m.resolve(now=WINDOW)) == [decision.NO_FACE]


@pytest.mark.parametrize("frame_at", [-WINDOW - 0.5, WINDOW + 0.5])
def test_a_frame_outside_the_window_does_not_count(frame_at):
    m, _ = build()
    if frame_at < 0:
        m.note_frame(ts=frame_at)
        tap(m, at=0.0)
    else:
        tap(m, at=0.0)
        m.note_frame(ts=frame_at)

    assert statuses(m.resolve(now=WINDOW + 1.0)) == [decision.UNVERIFIED]


def test_the_camera_is_judged_over_the_window_not_at_resolve_time():
    # Camera up while the first tap waits, then gone. Resolving late, with the camera
    # long dead, must not turn the watched tap into an unwatched one, and the reverse.
    m, _ = build()
    tap(m, at=0.0)
    m.note_frame(ts=2.0)  # camera watching tap 1
    watched = m.resolve(now=WINDOW + 30.0)  # resolved long after the last frame

    tap(m, at=100.0)  # camera dead for the whole of tap 2's window
    m.note_frame(ts=100.0 + WINDOW + 5.0)  # ...and back just before it is resolved
    unwatched = m.resolve(now=100.0 + WINDOW + 6.0)

    assert statuses(watched) == [decision.NO_FACE]
    assert statuses(unwatched) == [decision.UNVERIFIED]


def test_each_pending_tap_is_credited_separately():
    m, _ = build()
    m.add_tap("AAAAAAAA", "S001", [0.1], student=STUDENT, ts=0.0)
    m.add_tap("BBBBBBBB", "S002", [0.1], student=STUDENT, ts=10.0)
    m.note_frame(ts=1.0)  # inside the first window only

    outcomes = m.resolve(now=20.0)

    assert {o["uid"]: o["status"] for o in outcomes} == {
        "AAAAAAAA": decision.NO_FACE,
        "BBBBBBBB": decision.UNVERIFIED,
    }


def test_tap_is_not_resolved_before_its_window_closes():
    m, emitted = build()
    tap(m)

    assert m.resolve(now=WINDOW - 0.1) == []
    assert emitted == []


@pytest.mark.parametrize("frames", [0, 3])
def test_a_matched_face_is_accepted_whatever_the_frame_count(monkeypatch, frames):
    # The heartbeat only decides the verdict when no face was assigned. Assignment
    # needs numpy/scipy, which the minimal test environment stubs, so it is pinned.
    m, _ = build()
    monkeypatch.setattr(m, "_assign", lambda taps, faces: {0: 0})
    monkeypatch.setattr(matcher_mod.face, "cosine", lambda a, b: 0.86)
    tap(m)
    for i in range(frames):
        m.note_frame(ts=float(i))
    m.on_face({"track_id": 7, "embedding": [0.1, 0.2, 0.3], "is_live": True, "ts": 1.0})

    outcomes = m.resolve(now=WINDOW)

    assert statuses(outcomes) == [decision.ACCEPTED]
    assert outcomes[0]["face_score"] == 0.86 and outcomes[0]["track_id"] == 7
    assert outcomes[0]["camera_down"] is False


def test_the_track_memory_and_the_heartbeat_are_separate_settings():
    m = matcher_mod.Matcher(max_face_buffer=8, max_tailgated_tracks=3, camera_heartbeat=True)
    assert (m.max_face_buffer, m.max_tailgated_tracks, m.camera_heartbeat) == (8, 3, True)
    assert matcher_mod.Matcher().camera_heartbeat is False
