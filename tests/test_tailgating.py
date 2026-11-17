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


_unnamed = iter(range(1000, 2000))


def face_of(person):
    """A distinct unit embedding per person, so two people never look alike."""
    emb = [0.0] * 2048
    emb[person] = 1.0
    return emb


def face_event(m, track_id, at, person=None):
    """A face event. By default each track is its own person, and a face with no track
    id is a new person; pass `person` to show the same face on another track."""
    if person is None:
        person = track_id if track_id is not None else next(_unnamed)
    m.on_face({"track_id": track_id, "embedding": face_of(person), "is_live": True, "ts": at})


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


# --- PC-046: the tracker loses a person when frames stall ---


def test_a_lost_track_that_comes_back_as_a_new_one_is_not_flagged_again():
    # Frames stall for 30 s; the same face returns on a new track id.
    m, _ = build()
    face_event(m, track_id=1, at=0.0, person=7)
    assert statuses(m.resolve(now=4.0)) == [decision.TAILGATING]
    face_event(m, track_id=2, at=30.0, person=7)
    face_event(m, track_id=3, at=60.0, person=7)

    assert m.resolve(now=34.0) + m.resolve(now=64.0) == []


def test_the_same_face_after_the_dwell_gap_is_a_new_presence():
    m, _ = build(dwell_gap=60.0)
    face_event(m, track_id=1, at=0.0, person=7)
    m.resolve(now=4.0)
    face_event(m, track_id=2, at=90.0, person=7)

    assert statuses(m.resolve(now=94.0)) == [decision.TAILGATING]


def test_two_different_faces_at_once_are_two_rows():
    m, _ = build()
    face_event(m, track_id=1, at=0.0, person=7)
    face_event(m, track_id=2, at=0.0, person=8)

    assert statuses(m.resolve(now=4.0)) == [decision.TAILGATING, decision.TAILGATING]


def test_a_student_who_tapped_and_stays_is_not_flagged_when_the_track_is_lost(monkeypatch):
    m, _ = build()
    monkeypatch.setattr(m, "_assign", lambda taps, faces: {0: 0} if faces else {})
    monkeypatch.setattr(matcher_mod.face, "cosine", lambda a, b: 0.86)
    face_event(m, track_id=1, at=0.0, person=7)
    m.add_tap("C3BE343A", "S001", face_of(7), student=STUDENT, ts=1.0)
    assert statuses(m.resolve(now=5.0)) == [decision.ACCEPTED]

    face_event(m, track_id=9, at=25.0, person=7)

    assert m.resolve(now=29.0) == []


def test_a_dwell_gap_of_zero_turns_the_face_memory_off():
    m, _ = build(dwell_gap=0)
    face_event(m, track_id=1, at=0.0, person=7)
    m.resolve(now=4.0)
    face_event(m, track_id=2, at=5.0, person=7)

    assert statuses(m.resolve(now=9.0)) == [decision.TAILGATING]


def test_the_face_memory_is_bounded():
    m, _ = build(max_tailgated_tracks=2)
    for person in (7, 8, 9):
        face_event(m, track_id=person, at=0.0, person=person)
    m.resolve(now=4.0)
    assert len(m._dwells) == 2


def test_a_long_stall_on_a_slow_machine_gives_one_row_not_dozens():
    # The Mac bring-up (findings 5): one person for about a minute, frames 9-48 s apart,
    # a new track id after every stall.
    m, _ = build()
    seen, at, track = [], 0.0, 1
    for gap in (9, 14, 48, 11, 20, 30):
        face_event(m, track_id=track, at=at, person=7)
        seen += m.resolve(now=at + 4.0)
        at, track = at + gap, track + 1

    assert statuses(seen) == [decision.TAILGATING]


def mix(a, b, w):
    """Unit embedding w of the way from person a to person b."""
    import math
    emb = [0.0] * 2048
    emb[a], emb[b] = math.cos(w * math.pi / 2), math.sin(w * math.pi / 2)
    return emb


def test_the_remembered_face_does_not_drift_to_someone_else():
    # Each face is close to the one before it (cosine 0.92) and the first two are close
    # to the first face, so they are the same dwell. The last is close to the one before
    # it but far from the first (cosine 0.38). The memory keeps the first face, so the
    # last is flagged; a memory that took the newest face would have hidden it.
    m, _ = build()
    for n, w in enumerate((0.0, 0.25, 0.5)):
        m.on_face({"track_id": n + 1, "embedding": mix(7, 8, w), "is_live": True,
                   "ts": n * 5.0})
        m.resolve(now=n * 5.0 + 4.0)
    m.on_face({"track_id": 99, "embedding": mix(7, 8, 0.75), "is_live": True, "ts": 15.0})

    assert statuses(m.resolve(now=19.0)) == [decision.TAILGATING]


def test_a_look_alike_below_the_dwell_threshold_is_still_flagged():
    # cosine 0.55: above the 0.5 match threshold, below the 0.6 dwell threshold.
    import math
    m, _ = build()
    m.on_face({"track_id": 1, "embedding": face_of(7), "is_live": True, "ts": 0.0})
    m.resolve(now=4.0)
    w = math.acos(0.55) / (math.pi / 2)
    m.on_face({"track_id": 2, "embedding": mix(7, 8, w), "is_live": True, "ts": 5.0})

    assert statuses(m.resolve(now=9.0)) == [decision.TAILGATING]
