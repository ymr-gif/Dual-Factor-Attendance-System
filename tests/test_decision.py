"""Truth table for `backend.decision`: the pure function that turns the two factor
verdicts into one attendance status, and the rule for which statuses count as present.

Each factor is True (passed), False (explicitly failed) or None (could not run: no
camera, no enrolled reference, model error). The expected values below are written
out by hand, not derived, so a change to the rules has to be made in both places.
"""

import pytest

from backend import decision
from backend.decision import (
    ACCEPTED,
    FLAGGED,
    MISMATCH,
    NO_FACE,
    REJECTED,
    SPOOF,
    TAILGATING,
    UNREGISTERED,
    UNVERIFIED,
)

STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student"}
FACTOR_VALUES = (True, False, None)

# (face_match, liveness_pass) -> (status with enforce=False, status with enforce=True)
KNOWN_STUDENT_TABLE = {
    (True, True): (ACCEPTED, ACCEPTED),
    (True, None): (ACCEPTED, ACCEPTED),
    (None, True): (ACCEPTED, ACCEPTED),
    (None, None): (UNVERIFIED, UNVERIFIED),
    (False, True): (FLAGGED, REJECTED),
    (False, None): (FLAGGED, REJECTED),
    (False, False): (FLAGGED, REJECTED),
    (True, False): (FLAGGED, REJECTED),
    (None, False): (FLAGGED, REJECTED),
}

# status -> does the tap count as attendance?
PRESENT_TABLE = {
    ACCEPTED: True,
    FLAGGED: True,
    UNVERIFIED: True,
    UNREGISTERED: True,
    REJECTED: False,
    NO_FACE: False,
    MISMATCH: False,
    SPOOF: False,
    TAILGATING: False,
}


def test_table_covers_every_factor_combination():
    every_pair = {(face, live) for face in FACTOR_VALUES for live in FACTOR_VALUES}
    assert set(KNOWN_STUDENT_TABLE) == every_pair


@pytest.mark.parametrize("enforce", [False, True])
@pytest.mark.parametrize("liveness_pass", FACTOR_VALUES)
@pytest.mark.parametrize("face_match", FACTOR_VALUES)
def test_unknown_card_is_unregistered_whatever_the_factors_say(face_match, liveness_pass, enforce):
    assert decision.decide(None, face_match, liveness_pass, enforce=enforce) == UNREGISTERED


@pytest.mark.parametrize(("factors", "expected"), sorted(KNOWN_STUDENT_TABLE.items(), key=repr))
def test_known_student_truth_table(factors, expected):
    face_match, liveness_pass = factors
    not_enforcing, enforcing = expected
    assert decision.decide(STUDENT, face_match, liveness_pass, enforce=False) == not_enforcing
    assert decision.decide(STUDENT, face_match, liveness_pass, enforce=True) == enforcing


@pytest.mark.parametrize("enforce", [False, True])
def test_a_missing_factor_never_rejects(enforce):
    # Fail-open: None means "could not run", not "failed". With no explicit False
    # anywhere, enforcement must not turn the tap into a rejection.
    for face_match in (True, None):
        for liveness_pass in (True, None):
            status = decision.decide(STUDENT, face_match, liveness_pass, enforce=enforce)
            assert status in (ACCEPTED, UNVERIFIED)


def test_one_failed_factor_outweighs_a_passed_one():
    assert decision.decide(STUDENT, True, False, enforce=True) == REJECTED
    assert decision.decide(STUDENT, False, True, enforce=True) == REJECTED


@pytest.mark.parametrize(("flag", "expected"), [(False, FLAGGED), (True, REJECTED)])
def test_enforce_defaults_to_the_module_switch(monkeypatch, flag, expected):
    monkeypatch.setattr(decision, "ENFORCE_2FA", flag)
    assert decision.enforcing() is flag
    assert decision.decide(STUDENT, False, True) == expected
    # An explicit argument still wins over the switch.
    assert decision.decide(STUDENT, False, True, enforce=not flag) != expected


@pytest.mark.parametrize(("status", "present"), sorted(PRESENT_TABLE.items()))
def test_counts_as_present(status, present):
    assert decision.counts_as_present(status) is present


def test_every_status_constant_has_a_presence_ruling():
    # A status added to decision.py without a line in PRESENT_TABLE fails here,
    # because counts_as_present() treats any unlisted status as present.
    constants = {
        value
        for name, value in vars(decision).items()
        if name.isupper() and not name.startswith("_") and isinstance(value, str)
    }
    assert constants == set(PRESENT_TABLE)


def test_decide_only_returns_known_statuses():
    produced = {
        decision.decide(student, face_match, liveness_pass, enforce=enforce)
        for student in (None, STUDENT)
        for face_match in FACTOR_VALUES
        for liveness_pass in FACTOR_VALUES
        for enforce in (False, True)
    }
    assert produced == {UNREGISTERED, ACCEPTED, FLAGGED, REJECTED, UNVERIFIED}
