"""Enrollment at the kiosk must not land in the attendance data (18 Nov, Cabucos).

Two things the operator does at the reader and camera while enrolling used to be
logged as attendance: the card tapped to fill a UID on Register or Roster (an
`unregistered` row, or a full scan of an enrolled card), and the person standing at
the camera to have their face captured (`tailgating` rows).

- Card capture: Register or Roster arms it while its card field waits for a tap.
  The next card read is handed to that page as a `card_capture` event and is not
  logged. One card per arm; it ends by itself after a few seconds.
- Enrolling: the Register page keeps this on while it is open and visible, by
  calling `keep_enrolling` every few seconds. While it is on, a face with no tap is
  not flagged as tailgating. It ends by itself shortly after the page closes.

Both live in this process only and start off.
"""

import threading
import time

CARD_CAPTURE_MAX_SEC = 60.0
ENROLLING_SEC = 10.0  # how long one keep_enrolling call keeps enrollment on

_lock = threading.Lock()
_card_until = 0.0
_enrolling_until = 0.0


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


def take_card(now: float | None = None) -> bool:
    """True once when a card read is to be captured, not logged; the arm ends."""
    global _card_until
    now = time.time() if now is None else now
    with _lock:
        if now < _card_until:
            _card_until = 0.0
            return True
        return False


def keep_enrolling(now: float | None = None) -> None:
    global _enrolling_until
    now = time.time() if now is None else now
    with _lock:
        _enrolling_until = now + ENROLLING_SEC


def stop_enrolling() -> None:
    global _enrolling_until
    with _lock:
        _enrolling_until = 0.0


def active(now: float | None = None) -> bool:
    """Is someone enrolling at the camera now?"""
    now = time.time() if now is None else now
    with _lock:
        return now < _enrolling_until
