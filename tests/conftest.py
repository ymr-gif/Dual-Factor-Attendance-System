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
from datetime import datetime, timedelta, timezone
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
        self.revoked = {}  # uid -> {"student_id", "revoked_by"} (revoked_cards, PC-024)
        self.lookups = []  # every uid passed to find_student_by_uid
        self.logs = []  # every row "inserted" into attendance_logs
        self.reviews = []  # every row "inserted" into review_queue
        self.resolutions = {}  # review id -> how it was resolved (resolve_review)
        self.audits = []  # every row "inserted" into audit_log
        self.notifications = []  # every row "inserted" into notification_log
        self.send_took = timedelta(seconds=2)  # t1 - t0 of a DELIVERED row
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

    # PC-024, with the rules the real statements enforce.

    def _student(self, student_id):
        for uid, row in self.students.items():
            if row["student_id"] == student_id:
                return uid, row
        for row in getattr(self, "cardless", {}).values():
            if row["student_id"] == student_id:
                return None, row
        raise LookupError(f"no such student {student_id}")

    def _park(self, row):
        # A student between cards: kept here, off the uid -> row map.
        self.cardless = getattr(self, "cardless", {})
        self.cardless[row["student_id"]] = row

    def find_revoked_card(self, uid):
        r = self.revoked.get(uid)
        if r is None:
            return None
        _, row = self._student(r["student_id"])
        return {"student_id": row["student_id"], "name": row.get("name")}

    def mark_card_lost(self, student_id, actor):
        uid, row = self._student(student_id)
        if uid is None:
            raise ValueError("this student has no card to report lost")
        self.students.pop(uid)
        row["uid"] = None
        self._park(row)
        self.revoked[uid] = {"student_id": student_id, "revoked_by": actor}
        return {"student_id": student_id, "uid": None}

    def link_card(self, student_id, uid, actor):
        from backend.db import CardConflict

        current, row = self._student(student_id)
        if current == uid:
            raise CardConflict("this is already the student's card")
        if uid in self.revoked:
            raise CardConflict("this card was reported lost; mark it found first")
        if uid in self.students:
            raise CardConflict("this card is on another student")
        if current is not None:
            self.students.pop(current)
            self.revoked[current] = {"student_id": student_id, "revoked_by": actor}
        else:
            self.cardless.pop(student_id)
        row["uid"] = uid
        self.students[uid] = row
        return {"student_id": student_id, "uid": uid, "revoked_old": current is not None}

    def mark_card_found(self, student_id):
        current, row = self._student(student_id)
        if current is not None:
            raise ValueError("this student already has a card; report it lost first")
        mine = [u for u, r in self.revoked.items() if r["student_id"] == student_id]
        if not mine:
            raise LookupError("this student has no lost card")
        uid = mine[-1]
        del self.revoked[uid]
        self.cardless.pop(student_id)
        row["uid"] = uid
        self.students[uid] = row
        return {"student_id": student_id, "uid": uid}

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

    def resolve_review(self, review_id, resolution, resolved_by="operator",
                       identified_as=None):
        if resolution != "identified":
            identified_as = None
        elif not identified_as:
            raise LookupError("no student picked")
        if not 1 <= review_id <= len(self.reviews) or review_id in self.resolutions:
            raise ValueError(f"review {review_id} not found or already resolved")
        review = self.reviews[review_id - 1]
        if identified_as is not None and review["status"] != "tailgating":
            raise ValueError(f"review {review_id} is not a face with no tap")
        if identified_as is not None and not any(
            s["student_id"] == identified_as for s in self.students.values()
        ):
            raise LookupError(f"no such student {identified_as}")
        row = {"id": review_id, "log_id": review["log_id"], "status": review["status"],
               "resolution": resolution, "resolved_by": resolved_by,
               "identified_as": identified_as}
        self.resolutions[review_id] = row
        return row

    def insert_student(self, student_id, uid, name=None, guardian_email=None,
                       guardian_mobile=None):
        from backend.db import CardConflict

        if uid in self.revoked:
            raise CardConflict("this card was reported lost; mark it found first")
        if uid in self.students or any(
            s["student_id"] == student_id for s in self.students.values()
        ):
            raise ValueError("duplicate student_id or uid: (simulated)")
        row = {
            "student_id": student_id,
            "uid": uid,
            "name": name,
            "guardian_email": guardian_email,
            "guardian_mobile": guardian_mobile,
        }
        self.students[uid] = dict(row)
        return row

    def update_student(self, student_id, uid=None, name=None, guardian_email=None,
                       guardian_mobile=None):
        # Like the real one: only a value that is not None is written.
        from backend.db import CardConflict

        if uid is not None and uid in self.revoked:
            raise CardConflict("this card was reported lost; mark it found first")
        for row in self.students.values():
            if row["student_id"] == student_id:
                break
        else:
            raise ValueError(f"no student with student_id={student_id}")
        changes = {
            "uid": uid,
            "name": name,
            "guardian_email": guardian_email,
            "guardian_mobile": guardian_mobile,
        }
        row.update({k: v for k, v in changes.items() if v is not None})
        return {
            k: row.get(k)
            for k in ("student_id", "uid", "name", "guardian_email", "guardian_mobile")
        }

    def insert_audit(self, actor, action, target=None, detail=None):
        self.audits.append(
            {"actor": actor, "action": action, "target": target, "detail": detail}
        )

    # notification_log, with the rules the real statements enforce: one row per
    # (log_id, channel), a claim only on an unclaimed PENDING row, a finish only on
    # a PENDING row.

    def insert_notification(self, log_id, channel, t0, status="PENDING", error=None):
        if any(n["log_id"] == log_id and n["channel"] == channel
               for n in self.notifications):
            return None
        row = {
            "id": len(self.notifications) + 1,
            "log_id": log_id,
            "channel": channel,
            "t0": t0,
            "t1": None,
            "latency_ms": None,
            "status": status,
            "provider_message_id": None,
            "error": error,
            "attempts": 0,
            "claimed": False,
        }
        self.notifications.append(row)
        return dict(row)

    def _notification(self, notification_id):
        return next(n for n in self.notifications if n["id"] == notification_id)

    def claim_notification(self, notification_id):
        row = self._notification(notification_id)
        if row["status"] != "PENDING" or row["claimed"]:
            return False
        row["claimed"] = True
        row["attempts"] += 1
        return True

    def release_notification(self, notification_id, error=None):
        row = self._notification(notification_id)
        if row["status"] == "PENDING":
            row.update(claimed=False, error=error)

    def finish_notification(self, notification_id, status, provider_message_id=None,
                            error=None):
        row = self._notification(notification_id)
        if row["status"] != "PENDING":
            return None
        row.update(status=status, provider_message_id=provider_message_id, error=error,
                   claimed=False)
        if status == "DELIVERED":
            row["t1"] = row["t0"] + self.send_took
            row["latency_ms"] = round(self.send_took.total_seconds() * 1000)
        return dict(row)

    def get_notifications(self, date_from=None, date_to=None):
        return [dict(n) for n in self.notifications]

    def pending_notifications(self):
        out = []
        for n in self.notifications:
            if n["status"] != "PENDING":
                continue
            log = next((l for l in self.logs if l["id"] == n["log_id"]), {})
            student = next(
                (s for s in self.students.values()
                 if s["student_id"] == log.get("student_id")), {})
            out.append({
                "id": n["id"], "log_id": n["log_id"], "channel": n["channel"],
                "t0": n["t0"], "attempts": n["attempts"],
                "claimed_at": n["t0"] if n["claimed"] else None,
                "name": student.get("name"),
                "guardian_email": student.get("guardian_email"),
                "guardian_mobile": student.get("guardian_mobile"),
            })
        return out

    def patch_notifications(self, monkeypatch, db):
        for name in ("insert_notification", "claim_notification", "release_notification",
                     "finish_notification", "get_notifications", "pending_notifications"):
            monkeypatch.setattr(db, name, getattr(self, name))

    def delete_student(self, student_id, actor=None):
        """What the real erase does, over the rows held here."""
        from backend.db import STUDENT_AUDIT_ACTIONS, erase_detail, names_student

        student_id = (student_id or "").strip()
        counts = {"logs": 0, "students": 0, "notifications": 0, "audit_rows": 0, "uid": None,
                  "old_uids": []}
        uid = next(
            (u for u, s in self.students.items() if s["student_id"] == student_id), None
        )
        cardless = getattr(self, "cardless", {}).pop(student_id, None)
        old_uids = sorted(u for u, r in self.revoked.items() if r["student_id"] == student_id)
        cards = [u for u in [uid, *old_uids] if u]

        def about(a):
            return a["target"] == student_id and a["action"] in STUDENT_AUDIT_ACTIONS

        if not student_id or (
            uid is None and cardless is None and not any(about(a) for a in self.audits)
        ):
            return counts
        gone = {
            l["id"] for l in self.logs
            if l["student_id"] == student_id or (l["student_id"] is None and l["uid"] in cards)
        }
        counts["logs"] = len(gone)
        counts["notifications"] = sum(n["log_id"] in gone for n in self.notifications)
        counts["students"] = 1 if (self.students.pop(uid, None) or cardless) else 0
        for u in old_uids:
            del self.revoked[u]  # ON DELETE CASCADE
        self.logs = [l for l in self.logs if l["id"] not in gone]
        self.notifications = [n for n in self.notifications if n["log_id"] not in gone]
        self.reviews = [r for r in self.reviews if r["log_id"] not in gone]
        for r in self.resolutions.values():
            if r["identified_as"] == student_id:
                r["identified_as"] = None  # ON DELETE SET NULL
        for a in self.audits:
            if about(a):
                a.update(target=None, detail=None)
                counts["audit_rows"] += 1
            elif any(names_student(a["detail"], student_id, c) for c in cards or [None]):
                a["detail"] = None
                counts["audit_rows"] += 1
        if actor is not None:
            self.insert_audit(actor, "erase", None, erase_detail(counts))
        counts["uid"] = uid
        counts["old_uids"] = old_uids
        return counts

    def get_students(self):
        # The real query never selects face_embedding; mirror that.
        rows = [*self.students.values(), *getattr(self, "cardless", {}).values()]
        return [
            {**{k: v for k, v in row.items() if k != "face_embedding"},
             "lost_cards": sum(r["student_id"] == row["student_id"] for r in self.revoked.values())}
            for row in sorted(rows, key=lambda r: r["student_id"])
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

    Only `add_tap` exists, and `window`, which `/tap` reads for the live log: nothing
    else on the matcher may be touched by `/tap`.
    """

    window = 4.0

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
        self.published = []  # tap event dicts
        self.stages = []  # scan step events for the dashboard animation (livelog.stage)
        self.lines = []  # live log lines (livelog.record)
        self.notify_error = None

    def notify(self, student, log):
        if self.notify_error is not None:
            raise self.notify_error
        self.notified.append((student, log))

    def publish(self, event):
        {"stage": self.stages, "log": self.lines}.get(event.get("type"), self.published).append(event)


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


@pytest.fixture(autouse=True)
def settings_store(monkeypatch):
    """The runtime settings table, in memory. decision.enforcing() reads it on every
    decide(), so without this a test would open a connection to the real database."""
    from backend import db, liveness

    store = {}
    monkeypatch.setattr(liveness, "_saved", (None, -1e9))  # no cached read across tests
    monkeypatch.setattr(db, "get_setting", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(db, "set_setting", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(db, "get_all_settings", lambda: dict(sorted(store.items())))
    return store


@pytest.fixture
def sinks():
    return Sinks()


@pytest.fixture
def client(backend_main, monkeypatch, tmp_path, fake_db, camera, fake_matcher, sinks):
    """A TestClient with startup run and every external dependency replaced."""
    from fastapi.testclient import TestClient

    from backend import db, decision, events, face, liveness, perception, privacy
    from backend import notify as notify_mod

    # Database: startup migration, /health probe, /tap lookup + insert, review queue,
    # roster.
    monkeypatch.setattr(db, "init_db", fake_db.init_db)
    # The live log tees sys.stdout; under pytest that is a capture stream swapped per test.
    from backend import livelog

    monkeypatch.setattr(livelog, "install", lambda: None)
    monkeypatch.setattr(db, "get_conn", fake_db.get_conn)
    monkeypatch.setattr(db, "find_student_by_uid", fake_db.find_student_by_uid)
    for name in ("find_revoked_card", "mark_card_lost", "link_card", "mark_card_found"):
        monkeypatch.setattr(db, name, getattr(fake_db, name))
    monkeypatch.setattr(db, "insert_log", fake_db.insert_log)
    monkeypatch.setattr(db, "insert_review", fake_db.insert_review)
    monkeypatch.setattr(db, "get_students", fake_db.get_students)
    monkeypatch.setattr(db, "insert_student", fake_db.insert_student)
    monkeypatch.setattr(db, "update_student", fake_db.update_student)
    monkeypatch.setattr(db, "insert_audit", fake_db.insert_audit)
    fake_db.patch_notifications(monkeypatch, db)
    monkeypatch.setattr(db, "delete_student", fake_db.delete_student)
    monkeypatch.setattr(db, "resolve_review", fake_db.resolve_review)
    # The erase also cleans the serial reader's queue file; keep it off the real one.
    monkeypatch.setattr(privacy, "FAILED_TAPS_QUEUE", str(tmp_path / "failed_taps.jsonl"))

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
    monkeypatch.setattr(perception, "run_forever", lambda: perception_starts.append("run_forever"))
    monkeypatch.setattr(backend_main, "matcher", fake_matcher)

    # Side channels: guardian notify (console + SMTP) and the WebSocket event bus.
    monkeypatch.setattr(backend_main, "notify", sinks.notify)
    monkeypatch.setattr(events, "publish", sinks.publish)
    # The test message a saved contact gets: pinned off, so no test opens a socket.
    monkeypatch.setattr(notify_mod, "EMAIL_ENABLED", False)
    monkeypatch.setattr(notify_mod, "_send", _forbidden("notify._send (SMTP)"))
    # No SMS either: the Semaphore call is replaced in tests/test_sms.py only.
    monkeypatch.setattr(notify_mod, "SMS_ENABLED", False)
    monkeypatch.setattr(notify_mod, "SEMAPHORE_API_KEY", "")
    monkeypatch.setattr(notify_mod.requests, "post", _forbidden("requests.post (Semaphore)"))
    # No sender thread under test; tests/test_sender.py drives it by hand.
    monkeypatch.setattr(notify_mod, "start_sender", lambda: None)

    with TestClient(backend_main.app) as test_client:
        yield test_client

    assert perception_starts == [], "startup started the perception camera thread"
