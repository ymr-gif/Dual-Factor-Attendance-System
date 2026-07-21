"""Camera discovery and selection.

Mirrors backend/ports.py for the other pluggable device. The guardpost is usually
run on a laptop with a built-in camera, and an external USB camera is added when one
is available (better placement, and it frees the built-in camera for the browser).
Unset CAMERA_INDEX and the backend follows that: use the external camera when one is
present, fall back to the built-in one when it is not.

Enumeration is deliberately *passive* — nothing here opens a capture device. Probing
indices with cv2.VideoCapture would steal the camera from perception, which is the
single camera owner (design-notes §3), so we ask the OS what exists instead:
macOS via `system_profiler SPCameraDataType`, Linux via /sys/class/video4linux.

Caveat worth knowing: OpenCV addresses cameras by *index*, and neither OS gives us
that index directly. We map enumeration order to index, which matches AVFoundation
and V4L2 in the common case but is not guaranteed — a machine with several cameras
may need CAMERA_INDEX set explicitly. `builtin` is derived from the Apple vendor ID
(0x106B) / the "FaceTime" name on macOS, so external-vs-built-in is reliable even
when the index guess is not.

Env:
  CAMERA_INDEX            explicit index; used as-is when set (auto-selection off)
  CAMERA_PREFER_EXTERNAL  false -> prefer the built-in camera instead
  CAMERA_AUTO             false -> never auto-select, only ever use CAMERA_INDEX

CLI:
  python -m backend.cameras       list cameras and show which one would be used
"""

import glob
import json
import os
import subprocess
import time

APPLE_VENDOR_ID = "0x106b"
_BUILTIN_MARKERS = ("facetime", "isight", "built-in", "integrated")

# system_profiler takes ~1s; the API polls, so hold the result briefly.
_CACHE_TTL = 10.0
_cache: tuple[float, list] | None = None


def _looks_builtin(name: str, model: str) -> bool:
    blob = f"{name} {model}".lower()
    if APPLE_VENDOR_ID in blob:
        return True
    return any(m in blob for m in _BUILTIN_MARKERS)


def _macos_cameras() -> list:
    try:
        out = subprocess.run(
            ["system_profiler", "SPCameraDataType", "-json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(out.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []

    cameras = []
    for i, entry in enumerate(data.get("SPCameraDataType", [])):
        name = entry.get("_name") or f"camera {i}"
        model = entry.get("spcamera_model-id") or ""
        cameras.append({
            "index": i,
            "name": name,
            "model": model or None,
            "unique_id": entry.get("spcamera_unique-id"),
            "builtin": _looks_builtin(name, model),
        })
    return cameras


def _linux_cameras() -> list:
    cameras = []
    for path in sorted(glob.glob("/dev/video*")):
        digits = "".join(c for c in os.path.basename(path) if c.isdigit())
        if not digits:
            continue
        index = int(digits)
        name = f"video{index}"
        try:
            with open(f"/sys/class/video4linux/video{index}/name") as f:
                name = f.read().strip() or name
        except OSError:
            pass
        cameras.append({
            "index": index,
            "name": name,
            "model": None,
            "unique_id": None,
            "builtin": _looks_builtin(name, ""),
        })
    return cameras


def list_cameras(use_cache: bool = True) -> list:
    """Cameras the OS reports, in enumeration order. Never opens a device."""
    global _cache
    if use_cache and _cache and (time.time() - _cache[0]) < _CACHE_TTL:
        return _cache[1]
    cameras = _macos_cameras() if os.uname().sysname == "Darwin" else _linux_cameras()
    _cache = (time.time(), cameras)
    return cameras


def configured_index():
    """CAMERA_INDEX as an int, or None when unset/blank/not a number."""
    raw = os.environ.get("CAMERA_INDEX")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def prefer_external() -> bool:
    return os.environ.get("CAMERA_PREFER_EXTERNAL", "true").strip().lower() not in ("false", "0", "no")


def auto_enabled() -> bool:
    return os.environ.get("CAMERA_AUTO", "true").strip().lower() not in ("false", "0", "no")


def pick_index(default: int = 0) -> int:
    """The camera index to open.

    An explicit CAMERA_INDEX always wins. Otherwise prefer an external camera when
    one is plugged in and fall back to the built-in one — so plugging a USB camera
    in switches to it on the next restart without a config change.
    """
    configured = configured_index()
    if configured is not None or not auto_enabled():
        return configured if configured is not None else default

    cameras = list_cameras()
    if not cameras:
        return default

    external = [c for c in cameras if not c["builtin"]]
    builtin = [c for c in cameras if c["builtin"]]

    if prefer_external() and external:
        return external[0]["index"]
    if not prefer_external() and builtin:
        return builtin[0]["index"]
    return cameras[0]["index"]


def selected_camera():
    """The camera entry pick_index() resolves to, when we can identify it."""
    idx = pick_index()
    for c in list_cameras():
        if c["index"] == idx:
            return c
    return None


def describe(cam: dict) -> str:
    bits = [cam["name"], "built-in" if cam["builtin"] else "external"]
    if cam.get("model"):
        bits.append(cam["model"])
    return "  ·  ".join(bits)


def main():
    cameras = list_cameras(use_cache=False)
    chosen = pick_index()
    configured = configured_index()

    if not cameras:
        print("no cameras reported by the OS")
    else:
        print(f"{len(cameras)} camera(s):\n")
        for c in cameras:
            mark = "*" if c["index"] == chosen else " "
            print(f" {mark} index {c['index']}  {describe(c)}")
        print("\n * = the camera the backend would open")

    print()
    print(f"CAMERA_INDEX     {configured if configured is not None else '(unset)'}")
    print(f"auto-select      {'on' if auto_enabled() else 'off (CAMERA_AUTO=false)'}")
    print(f"prefers          {'external, falling back to built-in' if prefer_external() else 'built-in'}")
    print(f"would open       index {chosen}")

    if configured is not None:
        known = [c["index"] for c in cameras]
        if configured not in known:
            print(f"\nnote: CAMERA_INDEX={configured} is not in the reported list {known}; "
                  "it will still be tried as given.")
    print("\nThe backend must be restarted to change camera. On macOS it also needs a "
          "terminal that holds\nthe Camera permission — see 'make dev-cam'.")


if __name__ == "__main__":
    main()
