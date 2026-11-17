"""Runtime settings layer (Step 50). Precedence: DB > env > code default.

Only tunable performance/device/resolution keys are DB-overridable.
Infra values (DB_DSN, SMTP_*, OPERATOR_TOKEN) stay env-only.

Usage:
    from . import settings
    det_size = settings.get("face_det_size", default="320", cast=int)
"""

import os
from typing import Any

from . import db

# The keys that can be saved through the API, and that the code reads back at runtime.
# Only keys with a reader belong here; until 17 Nov the list held 21 keys, of which only
# enforce_2fa did anything. Everything else is set in `.env` and needs a restart.
#   enforce_2fa         decision.enforcing()
#   liveness_threshold  liveness.threshold(); empty = the model's own verdict
TUNABLE_KEYS = {
    "enforce_2fa",
    "liveness_threshold",
}


def get(key: str, default: str | None = None, cast: type = str) -> Any:
    """Read a setting: DB > env > default. Returns `cast(value)`."""
    raw = db.get_setting(key)
    if raw is not None:
        return _cast(raw, cast)
    env_val = os.environ.get(key.upper(), None)
    if env_val is not None:
        return _cast(env_val, cast)
    if default is not None:
        return _cast(default, cast)
    return None


# Switches: saved only as "true" or "false", so a typo cannot turn one off silently.
BOOL_KEYS = {"enforce_2fa", "use_gpu", "face_consent_required"}
# A score cutoff: a number from 0 to 1, or empty to clear it.
FRACTION_KEYS = {"liveness_threshold"}


def set(key: str, value: str) -> None:
    if key not in TUNABLE_KEYS:
        raise ValueError(f"'{key}' is not a tunable setting")
    if key in BOOL_KEYS and value not in ("true", "false"):
        raise ValueError(f"'{key}' must be true or false")
    if key in FRACTION_KEYS and value.strip():
        try:
            ok = 0.0 <= float(value) <= 1.0
        except ValueError:
            ok = False
        if not ok:
            raise ValueError(f"'{key}' must be a number from 0 to 1, or empty")
    db.set_setting(key, value)


def all_settings() -> dict[str, str]:
    return db.get_all_settings()


def _cast(raw: str, cast: type) -> Any:
    if cast == bool:
        return raw.lower() in ("1", "true", "yes", "on")
    return cast(raw)
