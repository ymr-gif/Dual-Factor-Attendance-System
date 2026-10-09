"""One verdict per presence: a face that stays in view is not flagged again and again.

Perception publishes a face event for a track when it is first recognized and again
every `FACE_REFRESH_SEC` while the track stays visible, so one person standing at the
reader arrives here as several `PendingFace`s with the same `track_id`. The matcher
must not turn the extra ones into `tailgating` rows: not after a tap claimed the
track, and not more than once when no tap did.

These tests drive `Matcher` with explicit timestamps; no camera, model or database.
Tap-to-face assignment needs numpy/scipy, which the minimal test environment stubs,
so the tests that need a pairing pin `_assign` and `face.cosine`.
"""

import pytest

from backend import decision
from backend import matcher as matcher_mod

WINDOW = 4.0
STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student"}


def build(**kwargs):
    emitted = []
    m = matcher_mod.Matcher(
        window=WINDOW,
        cooldown=2.0,
        threshold=0.5,
        tailgate_threshold=0.5,
        outcome_sink=emitted.append,
        face_search=None,
        clock=lambda: 0.0,
        **kwargs,
    )
    return m, emitted


def face_event(m, track_id, at):
    m.on_face({"track_id": track_id, "embedding": [0.1, 0.2, 0.3], "is_live": True, "ts": at})


def pin_pairing(monkeypatch, m, score=0.86):
    """Pair the first ripe tap with the first unclaimed face, at a fixed similarity."""
    monkeypatch.setattr(m, "_assign", lambda taps, faces: {0: 0} if faces else {})
    monkeypatch.setattr(matcher_mod.face, "cosine", lambda a, b: score)


def statuses(outcomes):
    return [o["status"] for o in outcomes]


def test_a_track_nobody_claims_is_flagged_once_however_long_it_stays():
    m, emitted = build()
    for at in (0.0, 2.0, 4.0, 6.0):
        face_event(m, track_id=1, at=at)

    seen = []
    for now in (4.0, 6.0, 8.0, 10.0, 12.0):
        seen += m.resolve(now=now)

    assert statuses(seen) == [decision.TAILGATING]
    assert seen[0]["track_id"] == 1
    assert emitted == seen


def test_an_accepted_tap_settles_the_later_refreshes_of_its_track(monkeypatch):
    # The student taps one second after stepping in and stays in view. The tap takes
    # one face event; the refreshes that follow are the same person, not a tailgater.
    m, _ = build()
    pin_pairing(monkeypatch, m)
    face_event(m, track_id=1, at=0.0)
    m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=1.0)
    for at in (2.0, 4.0, 6.0):
        face_event(m, track_id=1, at=at)

    seen = []
    for now in (5.0, 6.0, 8.0, 10.0, 12.0):
        seen += m.resolve(now=now)

    assert statuses(seen) == [decision.ACCEPTED]
    assert seen[0]["track_id"] == 1


def test_a_tap_that_did_not_match_settles_the_track_too(monkeypatch):
    # The face the tap was judged against is accounted for by that verdict.
    m, _ = build()
    pin_pairing(monkeypatch, m, score=0.1)
    face_event(m, track_id=1, at=0.0)
    m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=1.0)
    face_event(m, track_id=1, at=2.0)

    seen = m.resolve(now=5.0) + m.resolve(now=8.0)

    assert statuses(seen) == [decision.MISMATCH]


def test_a_second_person_on_another_track_is_still_flagged(monkeypatch):
    m, _ = build()
    pin_pairing(monkeypatch, m)
    face_event(m, track_id=1, at=0.0)
    m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=1.0)
    face_event(m, track_id=2, at=1.5)
    face_event(m, track_id=1, at=2.0)
    face_event(m, track_id=2, at=3.5)

    seen = []
    for now in (5.0, 6.0, 8.0):
        seen += m.resolve(now=now)

    assert statuses(seen) == [decision.ACCEPTED, decision.TAILGATING]
    assert seen[1]["track_id"] == 2


def test_a_flagged_track_can_still_be_claimed_by_a_later_tap(monkeypatch):
    # Face first, card more than one window later: the early flag stands, and the tap
    # is still judged against the refreshed face.
    m, _ = build()
    pin_pairing(monkeypatch, m)
    face_event(m, track_id=1, at=0.0)
    first = m.resolve(now=4.0)
    face_event(m, track_id=1, at=6.0)
    m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=6.5)

    later = m.resolve(now=10.5)

    assert statuses(first) == [decision.TAILGATING]
    assert statuses(later) == [decision.ACCEPTED]


def test_face_events_without_a_track_id_are_judged_one_by_one():
    # No track id means no presence to remember; two such faces are two verdicts.
    m, _ = build()
    face_event(m, track_id=None, at=0.0)
    face_event(m, track_id=None, at=0.5)

    assert statuses(m.resolve(now=5.0)) == [decision.TAILGATING, decision.TAILGATING]


def test_the_memory_of_settled_tracks_is_bounded():
    m, _ = build(max_tailgated_tracks=2)
    for track_id in (1, 2, 3):
        face_event(m, track_id=track_id, at=0.0)
    assert len(m.resolve(now=4.0)) == 3

    # Only two tracks are remembered. Track 1 was the oldest and has been forgotten, so
    # it is flagged afresh; tracks 2 and 3 are not.
    face_event(m, track_id=3, at=10.0)
    face_event(m, track_id=2, at=10.0)
    face_event(m, track_id=1, at=10.0)

    assert [o["track_id"] for o in m.resolve(now=14.0)] == [1]


def test_a_track_still_in_view_outlives_newer_tracks_in_the_bounded_memory():
    m, _ = build(max_tailgated_tracks=2)
    face_event(m, track_id=1, at=0.0)
    assert statuses(m.resolve(now=4.0)) == [decision.TAILGATING]
    face_event(m, track_id=2, at=4.0)
    face_event(m, track_id=1, at=4.0)
    assert [o["track_id"] for o in m.resolve(now=8.0)] == [2]
    face_event(m, track_id=3, at=8.0)
    face_event(m, track_id=1, at=8.0)

    # Track 1 was seen more recently than track 2, so track 2 is the one forgotten.
    assert [o["track_id"] for o in m.resolve(now=12.0)] == [3]


@pytest.mark.parametrize("cap", [0, -1])
def test_a_memory_of_no_tracks_flags_every_refresh_and_does_not_raise(cap):
    m, _ = build(max_tailgated_tracks=cap)
    face_event(m, track_id=1, at=0.0)
    face_event(m, track_id=1, at=2.0)

    assert statuses(m.resolve(now=4.0)) == [decision.TAILGATING]
    assert statuses(m.resolve(now=6.0)) == [decision.TAILGATING]
