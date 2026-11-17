"""Live backend log for the dashboard: every line the backend prints, as it happens.

`install()` puts a tee on stdout and stderr. Each complete line still goes to the
terminal or journal as before, and is also kept in a ring buffer (`recent()`, for a page
that opens late) and published on the tap WebSocket as `{"type": "log", ...}`.

`stage()` reports one step of a scan for the dashboard's scan animation
(`{"type": "stage", ...}`), and prints it, so the step is in the log too.

What leaves the backend this way is redacted first: email addresses, Philippine mobile
numbers and the values of secret settings (names with KEY, TOKEN, SECRET or PASSWORD)
never reach the guard's screen (PC-023, D1). Card UIDs, names and scores do, as on the
rest of the operator dashboard.

Fail-open like events.py: nothing here may break a print, and so a tap.
"""

import collections
import itertools
import os
import re
import sys
import threading
from datetime import datetime

from . import events

MAX_LINES = 500

_buf: collections.deque = collections.deque(maxlen=MAX_LINES)
_lock = threading.Lock()
_seq = itertools.count(1)
_installed = False

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_MOBILE = re.compile(r"(?<!\d)(\+?63|0)9\d{9}(?!\d)")


def _secrets():
    out = []
    for name, value in os.environ.items():
        if re.search(r"KEY|TOKEN|SECRET|PASSWORD", name) and value and len(value) >= 8:
            out.append(value)
    return out


def redact(text: str) -> str:
    for value in _secrets():
        text = text.replace(value, "<secret>")
    text = _EMAIL.sub("<email>", text)
    return _MOBILE.sub("<mobile>", text)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def record(text: str, source: str = "out") -> None:
    """Keep and publish one line (already without its newline)."""
    text = text.rstrip("\r")
    if not text.strip():
        return
    entry = {"seq": next(_seq), "ts": _now(), "source": source, "text": redact(text)}
    with _lock:
        _buf.append(entry)
    events.publish({"type": "log", **entry})


def recent(limit: int = 200) -> list:
    with _lock:
        lines = list(_buf)
    return lines[-max(limit, 0):] if limit else []


def stage(uid: str, step: str, text: str, done: bool = False) -> None:
    """One step of a scan, for the scan animation; printed into the log too."""
    try:
        print(f"[scan] {uid} {step}: {text}")
        events.publish({"type": "stage", "uid": uid, "stage": step, "text": redact(text),
                        "done": done, "ts": _now()})
    except Exception:
        pass


class _Tee:
    """A text stream that writes through and records each complete line."""

    def __init__(self, stream, source):
        self._stream = stream
        self._source = source
        self._partial = threading.local()

    def write(self, s):
        try:
            n = self._stream.write(s)
        except (ValueError, OSError):
            n = len(s)  # the stream underneath is closed; still record the line
        try:
            pending = getattr(self._partial, "text", "") + s
            *lines, rest = pending.split("\n")
            self._partial.text = rest
            for line in lines:
                record(line, self._source)
        except Exception:
            pass
        return n

    def flush(self):
        try:
            self._stream.flush()
        except (ValueError, OSError):
            pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install() -> None:
    """Tee stdout and stderr, once per process."""
    global _installed
    if _installed:
        return
    _installed = True
    sys.stdout = _Tee(sys.stdout, "out")
    sys.stderr = _Tee(sys.stderr, "err")
    # uvicorn's own log (startup, request errors with tracebacks) holds the stderr it
    # had before this ran, so it gets a handler of its own. Access lines are left out:
    # one per camera-state poll would bury the rest.
    import logging

    class _Handler(logging.Handler):
        def emit(self, rec):
            try:
                for line in self.format(rec).split("\n"):
                    record(line, "err")
            except Exception:
                pass

    h = _Handler()
    h.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logging.getLogger("uvicorn.error").addHandler(h)
