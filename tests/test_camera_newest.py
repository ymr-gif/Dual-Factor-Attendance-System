"""The perception loop works on what the camera sees now (18 Nov, MacBook lag).

A live camera is read on its own thread and only the newest read is kept, so frames
that came in while one was processed are skipped instead of queued. A video file is
still read frame by frame. Only the unused part of a frame's budget is slept.
"""

import threading
import time
import types

from backend import face, perception


class FakeCap:
    """Counts up one frame per read, `period` seconds apart; fails after `good` reads."""

    def __init__(self, period=0.002, good=None):
        self.period = period
        self.good = good
        self.n = 0
        self.released = False
        self.lock = threading.Lock()

    def isOpened(self):
        return True

    def read(self):
        time.sleep(self.period)
        with self.lock:
            self.n += 1
            n = self.n
        if self.good is not None and n > self.good:
            return False, None
        return True, n

    def release(self):
        self.released = True


def _use(monkeypatch, cap, live=True, fps=0.0):
    monkeypatch.setattr(face, "open_capture", lambda source=None: cap)
    monkeypatch.setattr(face, "CAMERA_WARMUP_FRAMES", 0)
    monkeypatch.setattr(perception, "_is_live_source", lambda: live)
    monkeypatch.setattr(perception, "PERCEPTION_FPS", fps)
    monkeypatch.setattr(perception, "_stats", perception._Stats())


def test_a_live_camera_skips_the_frames_that_came_in_while_one_was_processed(monkeypatch):
    cap = FakeCap()
    _use(monkeypatch, cap)
    frames = perception._camera_frames()
    first = next(frames)
    time.sleep(0.2)  # a slow frame: the camera keeps reading meanwhile
    second = next(frames)
    frames.close()
    assert second > first + 10  # the newest read, not the one queued after `first`
    assert perception._stats.skipped > 10
    assert cap.released


def test_a_video_file_is_read_frame_by_frame(monkeypatch):
    cap = FakeCap(period=0, good=5)
    _use(monkeypatch, cap, live=False)
    got = []
    for f in perception._camera_frames():
        got.append(f)
        time.sleep(0.01)
    assert got == [1, 2, 3, 4, 5]
    assert cap.released


def test_a_live_camera_that_stops_delivering_is_closed(monkeypatch):
    cap = FakeCap(period=0, good=0)
    _use(monkeypatch, cap)
    monkeypatch.setattr(perception, "CAMERA_MAX_MISSES", 3)
    assert list(perception._camera_frames()) == []
    assert cap.released


def test_only_the_unused_part_of_the_frame_budget_is_slept(monkeypatch):
    slept = []
    cap = FakeCap(period=0, good=3)
    _use(monkeypatch, cap, live=False, fps=20)  # budget 50 ms
    monkeypatch.setattr(perception, "time", types.SimpleNamespace(sleep=slept.append, time=time.time))
    frames = perception._camera_frames()
    next(frames)
    time.sleep(0.08)  # processing took longer than the budget: no extra wait
    next(frames)
    next(frames)  # processing took no time: about the whole budget is slept
    frames.close()
    assert len(slept) == 1
    assert 0.04 < slept[0] <= 0.05


def test_the_speed_line_reports_fps_detection_time_and_skipped_frames(monkeypatch, capsys):
    monkeypatch.setattr(perception, "PERCEPTION_STATS_SEC", 0.05)
    stats = perception._Stats()
    stats.skipped = 7
    stats.detected(0.1)
    time.sleep(0.06)
    stats.detected(0.3)
    out = capsys.readouterr().out
    assert "[perception]" in out and "fps" in out
    assert "detection 200 ms a frame" in out
    assert "7 camera frames skipped" in out
    assert stats.skipped == 0 and stats.frames == 0


def test_no_speed_line_when_turned_off(monkeypatch, capsys):
    monkeypatch.setattr(perception, "PERCEPTION_STATS_SEC", 0)
    stats = perception._Stats()
    time.sleep(0.01)
    stats.detected(0.1)
    assert capsys.readouterr().out == ""
