"""Shared test setup: make `backend.main` importable and inert.

The app talks to Postgres, a webcam, the face and liveness models and (optionally) an
SMTP server. None of that exists in a test run, so this file does three things:

1. Stubs third-party modules that are not installed, so the suite runs with only
   `requirements-dev.txt` (no CV stack, no database driver).
2. Imports `backend.main` once, with the built-SPA static mount skipped.
3. Hands each test a `TestClient` whose startup hooks, database calls, camera and
   notifications are replaced by the in-memory fakes below.

Nothing in `backend/` is changed to make this work; every replacement is a
`monkeypatch` of a module attribute that the app looks up at call time.
"""

import importlib.util
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest import mock

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)  # so `import backend` works under a bare `pytest`

# Top-level package -> the dotted names the backend imports from it.
#
# numpy, scipy, psycopg2 and pgvector are imported when backend.db / face / liveness /
# matcher load, so `backend.main` cannot be imported without them (or a stand-in).
# pyserial is imported when backend.ports loads, and backend.main imports that module
# for GET /api/serial/ports.
# cv2, onnxruntime, insightface and prometheus_client are imported inside functions
# only (camera, model load, /metrics). The tests replace those functions, so their
# stubs are a guard against an accidental real import, not a requirement.
_THIRD_PARTY = {
    "numpy": ["numpy"],
    "scipy": ["scipy", "scipy.optimize"],
    "psycopg2": ["psycopg2", "psycopg2.extras"],
    "pgvector": ["pgvector", "pgvector.psycopg2"],
    "cv2": ["cv2"],
    "onnxruntime": ["onnxruntime"],
    "insightface": ["insightface", "insightface.app", "insightface.app.common"],
    "prometheus_client": ["prometheus_client"],
    "serial": ["serial", "serial.tools", "serial.tools.list_ports"],
}


def _stub_missing_modules():
    """Put a MagicMock in sys.modules for each third-party module that is absent.

    Installed packages are left alone, so on a full dev machine the real modules are
    used. Returns the names that were stubbed (shown in the pytest header).
    """
    stubbed = []
    for package, names in _THIRD_PARTY.items():
        if importlib.util.find_spec(package) is not None:
            continue
        for name in names:
            module = mock.MagicMock(name=name)
            sys.modules[name] = module
            parent, _, child = name.rpartition(".")
            if parent:
                setattr(sys.modules[parent], child, module)
        stubbed.append(package)
    return stubbed


STUBBED_MODULES = _stub_missing_modules()


def pytest_report_header(config):
    if STUBBED_MODULES:
        return "nfc-scan: stubbed (not installed): " + ", ".join(STUBBED_MODULES)
    return "nfc-scan: third-party modules all installed, nothing stubbed"


@pytest.fixture(scope="session")
def backend_main():
    """`backend.main`, imported once.

    At import time the module mounts `frontend/dist` as static files when that
    directory exists. Whether the SPA has been built is irrelevant here, so the
    directory is reported as absent and the app is the same on every machine.
    """
    dist = os.path.realpath(os.path.join(REPO_ROOT, "frontend", "dist"))
    real_isdir = os.path.isdir

    def isdir(path):
        if os.path.realpath(path) == dist:
            return False
        return real_isdir(path)

    with mock.patch("os.path.isdir", isdir):
        import backend.main as module

    assert not any(
        getattr(route, "path", "").startswith("/app") for route in module.app.routes
    ), "SPA routes were mounted; the static-mount guard did not apply"
    return module


class FakeDB:
    """In-memory stand-in for the `backend.db` functions these tests reach.

    `insert_log` keeps the real keyword names and returns the same columns as the
    real `RETURNING` clause, so a renamed argument in the app fails here too.
    """

    def __init__(self):
        self.students = {}  # uid -> students row (dict)
        self.lookups = []  # every uid passed to find_student_by_uid
        self.logs = []  # every row "inserted" into attendance_logs
        self.reviews = []  # every row "inserted" into review_queue
        self.review_error = None
        self.init_calls = 0
        self.reachable = True

    def add_student(self, row):
        self.students[row["uid"]] = row
        return row

    def init_db(self):
        self.init_calls += 1

    @contextmanager
    def get_conn(self):
        if not self.reachable:
            raise ConnectionError("postgres is down (simulated)")
        yield mock.MagicMock(name="connection")

    def find_student_by_uid(self, uid):
        self.lookups.append(uid)
        return self.students.get(uid)

    def insert_log(
        self,
        uid,
        student_id,
        method,
        liveness_score=None,
        face_score=None,
        face_match=None,
        liveness_pass=None,
        status=None,
    ):
        row = {
            "id": len(self.logs) + 1,
            "uid": uid,
            "student_id": student_id,
            "ts": datetime(2026, 1, 5, 7, 30, tzinfo=timezone.utc),
            "method": method,
            "liveness_score": liveness_score,
            "face_score": face_score,
            "face_match": face_match,
            "liveness_pass": liveness_pass,
            "status": status,
        }
        self.logs.append(row)
        return row

    def insert_review(self, log_id, student_id, status, reason=None):
        if self.review_error is not None:
            raise self.review_error
        row = {"log_id": log_id, "student_id": student_id, "status": status, "reason": reason}
        self.reviews.append(row)
        return {"id": len(self.reviews)}

    def get_students(self):
        # The real query never selects face_embedding; mirror that.
        return [
            {k: v for k, v in row.items() if k != "face_embedding"}
            for row in self.students.values()
        ]


class FakeCamera:
    """What the camera and the two models report for the next tap.

    Default: no usable face. That is also what a missing or unplugged webcam looks
    like to `/tap` (`face.capture_probe()` returns None).
    """

    def __init__(self):
        self.probe = None
        self.score = None
        self.liveness = (None, None)
        self.captures = 0

    def sees(self, score, live_score, is_live):
        """A face is in frame: cosine `score` against the reference, plus the
        liveness model's `(live_score, is_live)` verdict."""
        from backend import face

        self.probe = face.Probe(frame="frame", bbox=(10, 10, 110, 110), embedding=[0.3, 0.2, 0.1])
        self.score = score
        self.liveness = (live_score, is_live)

    def capture_probe(self):
        self.captures += 1
        return self.probe

    def cosine(self, a, b):
        return self.score

    def assess(self, frame, bbox):
        return self.liveness


class FakeMatcher:
    """Records taps queued for async tap-to-face correlation (perception mode).

    Only `add_tap` exists: nothing else on the matcher may be touched by `/tap`.
    """

    def __init__(self):
        self.taps = []
        self.debounce = False

    def add_tap(self, uid, student_id, embedding, student=None, ts=None):
        if self.debounce:
            return None
        self.taps.append(
            {"uid": uid, "student_id": student_id, "embedding": embedding, "student": student}
        )
        return len(self.taps)


class Sinks:
    """Captures the two side channels of a tap: guardian notify and the WS bus."""

    def __init__(self):
        self.notified = []  # (student, log) pairs
        self.published = []  # event dicts
        self.notify_error = None

    def notify(self, student, log):
        if self.notify_error is not None:
            raise self.notify_error
        self.notified.append((student, log))

    def publish(self, event):
        self.published.append(event)


def _forbidden(what):
    def fail(*args, **kwargs):
        raise AssertionError(f"test reached real hardware or models: {what}")

    return fail


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def camera():
    return FakeCamera()


@pytest.fixture
def fake_matcher():
    return FakeMatcher()


@pytest.fixture
def sinks():
    return Sinks()


@pytest.fixture
def client(backend_main, monkeypatch, fake_db, camera, fake_matcher, sinks):
    """A TestClient with startup run and every external dependency replaced."""
    from fastapi.testclient import TestClient

    from backend import db, decision, events, face, liveness, perception, privacy

    # Database: startup migration, /health probe, /tap lookup + insert, review queue,
    # roster.
    monkeypatch.setattr(db, "init_db", fake_db.init_db)
    monkeypatch.setattr(db, "get_conn", fake_db.get_conn)
    monkeypatch.setattr(db, "find_student_by_uid", fake_db.find_student_by_uid)
    monkeypatch.setattr(db, "insert_log", fake_db.insert_log)
    monkeypatch.setattr(db, "insert_review", fake_db.insert_review)
    monkeypatch.setattr(db, "get_students", fake_db.get_students)

    # Behaviour switches are read from the environment at import. Pin them to the
    # code defaults so a developer's exported .env cannot change the results; a test
    # that wants another mode sets the attribute itself.
    monkeypatch.setattr(perception, "PERCEPTION_ENABLED", False)
    monkeypatch.setattr(decision, "ENFORCE_2FA", False)
    monkeypatch.setattr(face, "FACE_MATCH_ENABLED", True)
    monkeypatch.setattr(face, "FACE_THRESHOLD", 0.5)
    monkeypatch.setattr(liveness, "LIVENESS_ENABLED", True)
    monkeypatch.setattr(privacy, "FACE_CONSENT_REQUIRED", False)
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "")

    # Camera and models.
    monkeypatch.setattr(face, "capture_probe", camera.capture_probe)
    monkeypatch.setattr(face, "cosine", camera.cosine)
    monkeypatch.setattr(liveness, "assess", camera.assess)
    monkeypatch.setattr(face, "open_capture", _forbidden("face.open_capture (camera)"))
    monkeypatch.setattr(face, "get_app", _forbidden("face.get_app (InsightFace load)"))
    monkeypatch.setattr(liveness, "get_sessions", _forbidden("liveness.get_sessions (ONNX load)"))

    # Perception: the startup hook starts a camera-owner thread when it is enabled.
    # It is disabled above; these record a start if that ever stops being true.
    perception_starts = []
    monkeypatch.setattr(perception, "run", lambda *a, **k: perception_starts.append("run"))
    monkeypatch.setattr(perception, "_camera_frames", lambda: iter(()))
    monkeypatch.setattr(backend_main, "matcher", fake_matcher)

    # Side channels: guardian notify (console + SMTP) and the WebSocket event bus.
    monkeypatch.setattr(backend_main, "notify", sinks.notify)
    monkeypatch.setattr(events, "publish", sinks.publish)

    with TestClient(backend_main.app) as test_client:
        yield test_client

    assert perception_starts == [], "startup started the perception camera thread"
