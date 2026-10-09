"""The tap debounce: one card held at the reader is one tap, and a tap that could not
be queued is not mistaken for a repeat.

`Matcher.add_tap` is driven with explicit timestamps; no camera, model or database.
"""

import pytest

from backend import matcher as matcher_mod

STUDENT = {"student_id": "S001", "uid": "C3BE343A", "name": "Test Student"}


def build():
    return matcher_mod.Matcher(window=4.0, cooldown=2.0, threshold=0.5, clock=lambda: 0.0)


def tap(m, at):
    return m.add_tap("C3BE343A", "S001", [0.1, 0.2, 0.3], student=STUDENT, ts=at)


def test_a_repeat_read_inside_the_cooldown_is_debounced():
    m = build()
    assert tap(m, 0.0) == 1
    assert tap(m, 1.9) is None
    assert len(m._taps) == 1


def test_the_cooldown_counts_from_the_last_read_that_was_taken():
    # A debounced read must not push the cooldown out, or a held card never taps again.
    m = build()
    tap(m, 0.0)
    assert tap(m, 1.9) is None
    assert tap(m, 2.0) == 2, "a debounced read took a tap id or moved the cooldown"


def test_a_tap_that_could_not_be_built_is_not_debounced_on_retry(monkeypatch):
    # pgvector 0.5.x handed /tap a Vector that PendingTap could not convert: the first
    # request failed, and the retry was answered 'debounced' although nothing was queued.
    m = build()
    real = matcher_mod.PendingTap

    def unbuildable(*args, **kwargs):
        raise TypeError("float() argument must be a string or a real number, not 'Vector'")

    monkeypatch.setattr(matcher_mod, "PendingTap", unbuildable)
    with pytest.raises(TypeError):
        tap(m, 0.0)
    monkeypatch.setattr(matcher_mod, "PendingTap", real)

    assert tap(m, 0.5) is not None
    assert len(m._taps) == 1
