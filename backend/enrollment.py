"""Enrollment at the kiosk must not land in the attendance data (18 Nov, Cabucos).

Two things the operator does at the reader and camera while enrolling used to be
logged as attendance: the card tapped to fill a UID on Register or Roster (an
`unregistered` row, or a full scan of an enrolled card), and the person standing at
the camera to have their face captured (`tailgating` rows).

- Card capture: Register or Roster arms it once when its card field starts waiting
  for a tap. The next card read is handed to that page as a `card_capture` event and
  is not logged as attendance (it is audited, without the UID). One card per arm; it
  ends by itself. A lost card is never captured (main.py), so its tap stays `revoked`.
- Enrolling: the Register page keeps this on while it is open and visible, by
  calling `keep_enrolling` every few seconds. While it is on, a face with no tap is
  not flagged as tailgating. It ends ENROLLING_SEC after the last call, and in any
  case ENROLLING_MAX_SEC after it started; then the page must be closed and opened
  again. Start and end are audited (main.py).

Both live in this process only and start off.
"""

import threading
import time

CARD_CAPTURE_MAX_SEC = 60.0
ENROLLING_SEC = 10.0  # how long one keep_enrolling call keeps enrollment on
ENROLLING_MAX_SEC = 15 * 60.0  # one enrollment session at most, however long the page stays open

_lock = threading.Lock()
_card_until = 0.0
_enrolling_until = 0.0
_enrolling_since: float | None = None  # start of the current session; None after stop
_last_beat = 0.0


def arm_card(seconds: float = 20.0, now: float | None = None) -> float:
    """Take the next card read for enrollment, within `seconds` (capped). Returns
    when the arm ends."""
    global _card_until
    now = time.time() if now is None else now
    with _lock:
        _card_until = now + max(0.0, min(float(seconds), CARD_CAPTURE_MAX_SEC))
        return _card_until


def disarm_card() -> None:
    global _card_until
    with _lock:
        _card_until = 0.0


def armed(now: float | None = None) -> bool:
    now = time.time() if now is None else now
    with _lock:
        return now < _card_until


def take_card(now: float | None = None) -> bool:
    """True once when a card read is to be captured, not logged; the arm ends."""
    global _card_until
    now = time.time() if now is None else now
    with _lock:
        if now < _card_until:
            _card_until = 0.0
            return True
        return False


def keep_enrolling(now: float | None = None) -> bool:
    """Extend the enrollment session; False once it has reached ENROLLING_MAX_SEC."""
    global _enrolling_until, _enrolling_since
    now = time.time() if now is None else now
    global _last_beat
    with _lock:
        # No call for longer than ENROLLING_SEC: the page was closed (or the browser
        # went away without saying so); this is a new session.
        if _enrolling_since is None or now - _last_beat > ENROLLING_SEC:
            _enrolling_since = now
        _last_beat = now
        if now - _enrolling_since >= ENROLLING_MAX_SEC:
            _enrolling_until = 0.0
            return False
        _enrolling_until = min(now + ENROLLING_SEC, _enrolling_since + ENROLLING_MAX_SEC)
        return True


def stop_enrolling() -> None:
    global _enrolling_until, _enrolling_since
    with _lock:
        _enrolling_until = 0.0
        _enrolling_since = None


def active(now: float | None = None) -> bool:
    """Is someone enrolling at the camera now?"""
    now = time.time() if now is None else now
    with _lock:
        return now < _enrolling_until
