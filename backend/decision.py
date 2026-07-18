"""Attendance verification decision / buddy-punch enforcement (Step 9).

NFC identifies the student; face match (Step 6) + liveness (Step 7) verify it's
really them. This module collapses the raw per-factor verdicts into one attendance
`status`, and — when ENFORCE_2FA is on — rejects a tap whose 2nd factor failed
(the buddy-punch / photo-spoof case: someone taps a friend's card, or presents a
printed photo of the enrolled student).

Fail-open is preserved: a factor that could not run (no camera, no enrolled
reference, model error) is None, never a failure. Enforcement rejects only on an
*explicit* False, so a missing webcam still logs attendance exactly as before.
"""

import os

ENFORCE_2FA = os.environ.get("ENFORCE_2FA", "false").lower() in ("1", "true", "yes", "on")

# status values written to attendance_logs.status
UNREGISTERED = "unregistered"  # no student row for this uid
REJECTED = "rejected"  # enforcing and a factor explicitly failed -> not counted present
FLAGGED = "flagged"  # a factor failed but enforcement off -> logged present, warned
UNVERIFIED = "unverified"  # student known, no verdict available (fail-open)
ACCEPTED = "accepted"  # every available factor passed


def enforcing() -> bool:
    return ENFORCE_2FA


def decide(student, face_match, liveness_pass, enforce=None) -> str:
    """Collapse the per-factor verdicts into one attendance status.

    student:       the students row (dict) or None
    face_match:    True / False / None (None = check could not run)
    liveness_pass: True / False / None
    enforce:       override ENFORCE_2FA (mainly for tests)
    """
    if enforce is None:
        enforce = ENFORCE_2FA
    if student is None:
        return UNREGISTERED
    failed = face_match is False or liveness_pass is False
    if failed:
        return REJECTED if enforce else FLAGGED
    if face_match is True or liveness_pass is True:
        return ACCEPTED
    return UNVERIFIED  # all factors None — nothing to verify against


def counts_as_present(status: str) -> bool:
    """True when the tap should count as attendance. Only a hard REJECTED does not."""
    return status != REJECTED
