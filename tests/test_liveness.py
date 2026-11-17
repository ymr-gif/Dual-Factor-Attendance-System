"""Liveness preprocessing: the MiniFASNet models take raw 0-255 pixels."""

import numpy as np
import pytest

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


# --- the threshold saved on the Settings page ---


def test_a_saved_threshold_wins_over_the_env_one(monkeypatch, settings_store):
    monkeypatch.setattr(liveness, "LIVENESS_THRESHOLD", 0.3)
    assert liveness.threshold() == 0.3 and liveness.calibrated()
    settings_store["liveness_threshold"] = "0.75"
    monkeypatch.setattr(liveness, "_saved", (None, -1e9))
    assert liveness.threshold() == 0.75


def test_an_empty_saved_threshold_means_the_model_verdict(monkeypatch, settings_store):
    monkeypatch.setattr(liveness, "LIVENESS_THRESHOLD", 0.3)
    settings_store["liveness_threshold"] = ""
    assert liveness.threshold() is None and not liveness.calibrated()


def test_the_saved_threshold_decides_is_live(monkeypatch, settings_store):
    sessions = [(_Session(), 2.7), (_Session(), 4.0)]  # p_live ~0.987
    monkeypatch.setattr(liveness, "get_sessions", lambda: sessions)
    settings_store["liveness_threshold"] = "0.99"
    frame = np.full((480, 640, 3), 200, dtype=np.uint8)
    assert liveness.assess(frame, [270, 190, 370, 290])[1] is False


def test_an_unreadable_setting_falls_back(monkeypatch):
    from backend import db

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(db, "get_setting", boom)
    monkeypatch.setattr(liveness, "LIVENESS_THRESHOLD", 0.4)
    assert liveness.threshold() == 0.4


def test_the_settings_page_only_offers_keys_the_code_reads():
    from backend import settings

    assert settings.TUNABLE_KEYS == {"enforce_2fa", "liveness_threshold"}


@pytest.mark.parametrize("value", ["1.5", "-0.1", "abc"])
def test_a_threshold_outside_0_to_1_is_refused(value):
    from backend import settings

    with pytest.raises(ValueError):
        settings.set("liveness_threshold", value)


def test_a_threshold_in_range_or_empty_is_saved(settings_store):
    from backend import settings

    settings.set("liveness_threshold", "0.62")
    settings.set("liveness_threshold", "")
    assert settings_store["liveness_threshold"] == ""
