"""Liveness preprocessing: the MiniFASNet models take raw 0-255 pixels."""

import numpy as np

from backend import liveness


class _Input:
    name = "input"


class _Session:
    def __init__(self):
        self.blobs = []

    def get_inputs(self):
        return [_Input()]

    def run(self, _outputs, feed):
        self.blobs.append(feed["input"])
        return [np.array([[0.0, 5.0, 0.0]])]


def test_blob_is_unscaled_bgr(monkeypatch):
    sessions = [(_Session(), 2.7), (_Session(), 4.0)]
    monkeypatch.setattr(liveness, "get_sessions", lambda: sessions)
    monkeypatch.setattr(liveness, "LIVENESS_THRESHOLD", None)
    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    score, is_live = liveness.assess(frame, [270, 190, 370, 290])
    for sess, _ in sessions:
        blob = sess.blobs[0]
        assert blob.shape == (1, 3, 80, 80)
        assert blob.max() == 200.0
    assert score > 0.9 and is_live is True
