"""Face events: when a track is recognized, and what a refresh may publish.

A track is recognized on its first usable frame. While it stays visible it publishes
a face event again every `FACE_REFRESH_SEC`, so a tap that comes late can still claim
the face. A refresh of an unbroken track reuses the cached embedding. A track that
lost its face for a frame or more may have passed to another person, so its next
refresh recognizes again instead of replaying the first person's identity. A pause
with no processed frame at all is treated the same way.

`process_frame` is driven with a fake detector, recognizer and clock. A "frame" here
is just the list of (person, bbox) pairs in view; no camera or model is involved.
"""

import types

import pytest

from backend import face, liveness, perception

SPOT = (100, 100, 300, 300)
SAME_SPOT = (120, 110, 320, 310)  # overlaps SPOT well above TRACK_IOU_THRESH
NEAR = (100, 100, 200, 200)  # 100 px: large enough to recognize
FAR = (110, 110, 185, 185)  # 75 px: below MIN_FACE_PX, overlaps NEAR enough to keep the track
FPS = 10


class Scene:
    """Feeds frames to perception.process_frame at a fixed rate on a fake clock."""

    def __init__(self, monkeypatch):
        self.now = 0.0
        self.events = []  # face events, in order
        self.recognized = []  # who the recognizer was run on, in order
        self.tracker = perception.FaceTracker(iou_thresh=0.3, max_misses=15)

        def detect(frame):
            return [face.Detection(bbox, None, 0.9) for _, bbox in frame]

        def embed(frame, det):
            who = next(person for person, bbox in frame if bbox == det.bbox)
            self.recognized.append(who)
            return "embedding-of-" + who

        monkeypatch.setattr(face, "detect", detect)
        monkeypatch.setattr(face, "embed", embed)
        monkeypatch.setattr(face, "MIN_FACE_PX", 80)
        monkeypatch.setattr(liveness, "enabled", lambda: False)
        monkeypatch.setattr(perception, "FACE_REFRESH_SEC", 2.0)
        monkeypatch.setattr(perception, "TRACK_STALE_SEC", 1.0)
        monkeypatch.setattr(perception, "time", types.SimpleNamespace(time=lambda: self.now))
        monkeypatch.setattr(perception, "_face_sinks", [self.events.append])
        monkeypatch.setattr(perception, "_frame_sinks", [])

    def show(self, frame, until):
        """Hold `frame` in view from the current time up to `until` (seconds)."""
        while self.now < until - 1e-9:
            perception.process_frame(frame, self.tracker)
            self.now = round(self.now + 1.0 / FPS, 6)

    def published(self):
        return [(e["ts"], e["track_id"], e["embedding"]) for e in self.events]


@pytest.fixture
def scene(monkeypatch):
    return Scene(monkeypatch)


def test_a_track_is_recognized_once_and_nothing_is_published_before_the_refresh(scene):
    scene.show([("A", SPOT)], until=1.9)

    assert scene.recognized == ["A"]
    assert scene.published() == [(0.0, 1, "embedding-of-A")]


def test_an_unbroken_track_refreshes_from_the_cache_without_recognizing_again(scene):
    scene.show([("A", SPOT)], until=6.5)

    assert scene.recognized == ["A"]
    assert scene.published() == [
        (0.0, 1, "embedding-of-A"),
        (2.0, 1, "embedding-of-A"),
        (4.0, 1, "embedding-of-A"),
        (6.0, 1, "embedding-of-A"),
    ]


def test_a_track_that_changed_hands_is_recognized_again(scene):
    # A leaves; B stands in the same spot before the track expires and inherits its id.
    scene.show([("A", SPOT)], until=3.0)
    scene.show([], until=3.5)
    scene.show([("B", SAME_SPOT)], until=6.5)

    assert scene.recognized == ["A", "B"]
    assert scene.published() == [
        (0.0, 1, "embedding-of-A"),
        (2.0, 1, "embedding-of-A"),
        (4.0, 1, "embedding-of-B"),
        (6.0, 1, "embedding-of-B"),
    ]


def test_a_detector_dropout_costs_one_recognition_at_the_next_refresh(scene):
    scene.show([("A", SPOT)], until=0.5)
    scene.show([], until=0.7)
    scene.show([("A", SPOT)], until=1.0)
    scene.show([], until=1.2)
    scene.show([("A", SPOT)], until=4.5)

    assert scene.recognized == ["A", "A"]
    assert [ts for ts, _, _ in scene.published()] == [0.0, 2.0, 4.0]


def test_a_face_too_small_to_recognize_is_not_refreshed(scene):
    scene.show([("A", NEAR)], until=1.0)
    scene.show([("A", FAR)], until=5.0)

    assert len(scene.tracker._tracks) == 1  # same track throughout
    assert scene.published() == [(0.0, 1, "embedding-of-A")]


def test_a_refresh_that_recognizes_again_also_checks_liveness_again(scene, monkeypatch):
    verdicts = iter([(0.9, True), (0.2, False)])
    monkeypatch.setattr(liveness, "enabled", lambda: True)
    monkeypatch.setattr(liveness, "assess", lambda frame, bbox: next(verdicts))

    scene.show([("A", SPOT)], until=1.0)
    scene.show([], until=1.3)
    scene.show([("B", SAME_SPOT)], until=2.5)

    assert [(e["embedding"], e["is_live"]) for e in scene.events] == [
        ("embedding-of-A", True),
        ("embedding-of-B", False),
    ]


def test_one_missed_frame_is_enough_to_recognize_again(scene):
    scene.show([("A", SPOT)], until=1.0)
    scene.show([], until=1.1)  # exactly one frame without the face
    scene.show([("B", SAME_SPOT)], until=2.5)

    assert scene.recognized == ["A", "B"]
    assert scene.published() == [(0.0, 1, "embedding-of-A"), (2.0, 1, "embedding-of-B")]


def test_a_track_that_changed_hands_while_too_small_is_recognized_when_it_is_usable(scene):
    scene.show([("A", NEAR)], until=1.0)
    scene.show([], until=1.3)
    scene.show([("B", FAR)], until=3.0)  # B inherits the track but is too small to publish
    scene.show([("B", NEAR)], until=3.5)

    assert len(scene.tracker._tracks) == 1
    assert scene.recognized == ["A", "B"]
    assert [e[2] for e in scene.published()] == ["embedding-of-A", "embedding-of-B"]


def test_a_face_that_starts_too_small_is_not_recognized_until_it_is_usable(scene):
    scene.show([("A", FAR)], until=1.0)
    assert scene.recognized == [] and scene.published() == []
    scene.show([("A", NEAR)], until=1.5)
    assert scene.recognized == ["A"]


def test_a_pause_with_no_processed_frame_counts_as_a_missed_frame(scene):
    # The camera delivers nothing from 1.0 to 3.0 s (failed reads, a stalled loop). The
    # tracker sees no empty frame, so only the clock shows that B could have replaced A.
    scene.show([("A", SPOT)], until=1.0)
    scene.now = 3.0
    scene.show([("B", SAME_SPOT)], until=3.5)

    assert len(scene.tracker._tracks) == 1
    assert scene.recognized == ["A", "B"]
    assert scene.published() == [(0.0, 1, "embedding-of-A"), (3.0, 1, "embedding-of-B")]


def test_a_pause_shorter_than_the_stale_limit_does_not_cost_a_recognition(scene):
    scene.show([("A", SPOT)], until=1.0)
    scene.now = 1.8  # 0.9 s since the last processed frame, under TRACK_STALE_SEC
    scene.show([("A", SPOT)], until=2.5)

    assert scene.recognized == ["A"]
    assert scene.published() == [(0.0, 1, "embedding-of-A"), (2.0, 1, "embedding-of-A")]


def test_time_spent_recognizing_is_not_mistaken_for_a_pause(scene, monkeypatch):
    # Recognition is slow. If the pause were measured from the start of the previous
    # frame, one slow recognition would mark every track stale and trigger the next.
    def slow_embed(frame, det):
        scene.recognized.append("A")
        scene.now += 1.5
        return "embedding-of-A"

    monkeypatch.setattr(face, "embed", slow_embed)
    scene.show([("A", SPOT)], until=8.0)

    assert scene.recognized == ["A"]


def test_a_recognition_that_fails_leaves_the_track_due_for_another(scene, monkeypatch):
    def assess(frame, bbox):
        if scene.now == 2.0:
            raise RuntimeError("liveness model failed")
        return 0.9, True

    monkeypatch.setattr(liveness, "enabled", lambda: True)
    monkeypatch.setattr(liveness, "assess", assess)

    scene.show([("A", SPOT)], until=1.0)
    scene.show([], until=1.3)
    with pytest.raises(RuntimeError):
        scene.show([("B", SAME_SPOT)], until=2.05)  # the refresh at 2.0 fails
    scene.now = 2.1
    scene.show([("B", SAME_SPOT)], until=2.5)

    # B was measured in full on the next frame: an embedding and a liveness verdict.
    assert [(e["ts"], e["embedding"], e["is_live"]) for e in scene.events] == [
        (0.0, "embedding-of-A", True),
        (2.1, "embedding-of-B", True),
    ]
