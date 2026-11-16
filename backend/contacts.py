"""Guardian contact formats (PC-019).

A badly typed number or address is refused when the student is saved, not found out
later when a message fails. One stored form per contact, so the sender never has to
guess what it is holding.

Mobile: Philippine mobile numbers only, typed as `09XXXXXXXXX` or `+639XXXXXXXXX`
(spaces, dashes, dots and brackets are ignored). Stored as `09XXXXXXXXX`, the form
Semaphore's API documentation uses for its `number` parameter.

Every function raises ValueError with a message that is safe to show the operator:
it describes the expected format and never repeats what was typed.
"""

import re

_SEPARATORS = re.compile(r"[\s\-.()]")
_MOBILE = re.compile(r"(?:\+63|0)(9\d{9})")
# Deliberately loose: one @, something on both sides, a dot in the domain. Whether the
# mailbox exists is what the test message on save is for.
_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")
_EMAIL_MAX = 254

MOBILE_HINT = "guardian mobile must look like 09XXXXXXXXX or +639XXXXXXXXX"
EMAIL_HINT = "guardian email must look like name@example.com"


def normalize_mobile(raw: str | None) -> str | None:
    """`09XXXXXXXXX` for a valid number, None for a blank one. ValueError otherwise."""
    if raw is None:
        return None
    digits = _SEPARATORS.sub("", raw)
    if not digits:
        return None
    m = _MOBILE.fullmatch(digits)
    if not m:
        raise ValueError(MOBILE_HINT)
    return "0" + m.group(1)


def normalize_email(raw: str | None) -> str | None:
    """The address with outer spaces removed, None for a blank one. ValueError when it
    cannot be an address."""
    if raw is None:
        return None
    email = raw.strip()
    if not email:
        return None
    if len(email) > _EMAIL_MAX or not _EMAIL.fullmatch(email):
        raise ValueError(EMAIL_HINT)
    return email
