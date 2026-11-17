"""PC-033: a live camera that stops, or is not plugged in, is reopened; no restart.

run_forever() runs the pipeline on the camera and, when the frames stop, tries again
every CAMERA_RETRY_SEC. A video file runs once.
"""

from backend import perception


def _rounds(monkeypatch, source, outcomes):
    """Run run_forever with a fake camera: each round yields `outcomes[i]` frames
    (0 = no camera). Returns the sleeps between rounds."""
    monkeypatch.setattr(perception, "PERCEPTION_SOURCE", source)
    monkeypatch.setattr(perception, "process_frame", lambda frame, tr: setattr(tr, "last_done_ts", 1.0))
    opened = iter(outcomes)
    monkeypatch.setattr(perception, "_camera_frames", lambda: iter(["f"] * next(opened)))
    sleeps = []
    perception.run_forever(sleep=sleeps.append, max_rounds=len(outcomes))
    return sleeps


def test_a_camera_that_stops_is_reopened(monkeypatch, capsys):
    monkeypatch.setattr(perception, "CAMERA_RETRY_SEC", 5.0)
    # frames, then unplugged twice, then plugged back
    sleeps = _rounds(monkeypatch, None, [3, 0, 0, 2])
    assert sleeps == [5.0, 5.0, 5.0]
    # said once per outage, not on every try
    assert capsys.readouterr().out.count("no camera") == 1


def test_a_device_path_is_a_live_camera(monkeypatch):
    assert len(_rounds(monkeypatch, "/dev/video2", [0, 1])) == 1


def test_a_video_file_runs_once(monkeypatch):
    assert _rounds(monkeypatch, "clip.mp4", [5, 5]) == []


def test_a_pipeline_error_does_not_end_the_loop(monkeypatch):
    monkeypatch.setattr(perception, "PERCEPTION_SOURCE", None)
    calls = []

    def run(frames):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("model crashed")
        return perception.FaceTracker()

    monkeypatch.setattr(perception, "run", run)
    monkeypatch.setattr(perception, "_camera_frames", lambda: iter(()))
    perception.run_forever(sleep=lambda s: None, max_rounds=2)
    assert len(calls) == 2
