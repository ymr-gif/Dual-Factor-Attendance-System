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

# The set of keys that can be read/written via the API.
TUNABLE_KEYS = {
    "face_det_size",
    "min_face_px",
    "face_threshold",
    "liveness_threshold",
    "camera_index",
    "camera_resolution",
    "perception_fps",
    "track_iou_thresh",
    "track_max_misses",
    "assoc_window_sec",
    "tap_cooldown_sec",
    "match_threshold",
    "tailgate_name_threshold",
    "use_gpu",
    "enforce_2fa",
    "face_consent_required",
    "attendance_retention_days",
    "score_retention_days",
    "reenroll_after_days",
    "dup_enroll_threshold",
    "late_cutoff",
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


def set(key: str, value: str) -> None:
    if key not in TUNABLE_KEYS:
        raise ValueError(f"'{key}' is not a tunable setting")
    db.set_setting(key, value)


def all_settings() -> dict[str, str]:
    return db.get_all_settings()


def _cast(raw: str, cast: type) -> Any:
    if cast == bool:
        return raw.lower() in ("1", "true", "yes", "on")
    return cast(raw)
