"""CAMERA_WIDTH / CAMERA_HEIGHT: asked of a live camera only, and a size the camera
does not give is reported. cv2.VideoCapture is replaced; no camera is opened."""

import cv2
import pytest

from backend import face


class FakeCapture:
    def __init__(self, source, gives=(640, 480)):
        self.source, self.asked, self.gives = source, {}, list(gives)

    def set(self, prop, value):
        self.asked[prop] = value
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            self.gives[0] = value
        return True

    def get(self, prop):
        return self.gives[0] if prop == cv2.CAP_PROP_FRAME_WIDTH else self.gives[1]


@pytest.fixture
def opened(monkeypatch):
    made = []

    def capture(source):
        made.append(FakeCapture(source))
        return made[-1]

    monkeypatch.setattr(cv2, "VideoCapture", capture)
    return made


def size(monkeypatch, width, height):
    monkeypatch.setattr(face, "CAMERA_WIDTH", width)
    monkeypatch.setattr(face, "CAMERA_HEIGHT", height)


def test_unset_asks_nothing(opened, monkeypatch):
    size(monkeypatch, None, None)

    face.open_capture(0)

    assert opened[0].asked == {}


@pytest.mark.parametrize("source", [0, "1", "/dev/video2"])
def test_a_live_camera_is_asked_for_the_size(opened, monkeypatch, source):
    size(monkeypatch, 1280, 720)

    face.open_capture(source)

    assert opened[0].asked == {cv2.CAP_PROP_FRAME_WIDTH: 1280, cv2.CAP_PROP_FRAME_HEIGHT: 720}


def test_a_video_file_is_left_alone(opened, monkeypatch):
    size(monkeypatch, 1280, 720)

    face.open_capture("clips/entry.mp4")

    assert opened[0].asked == {}


def test_a_size_the_camera_does_not_give_is_printed(opened, monkeypatch, capsys):
    size(monkeypatch, 1280, 720)  # the fake keeps its height at 480

    face.open_capture(0)

    assert "asked for 1280x720, the camera gives 1280x480" in capsys.readouterr().out
