"""Continuous perception service (Step 30, Flow track).

One long-running process owns the camera and runs detect -> track -> recognize
*continuously*, so cost is per-*track*, not per-*frame*. It is the single camera
owner (design-notes §3): `face.capture_probe()` and `preview.py` must not touch the
same camera while this runs.

It fans out two in-process streams via registered sinks:

  - **frame events** ``{type:'frame', ts, tracks:[{track_id, bbox, recognized}]}``
    -> boxes-only viewer (Step 35). Box geometry only — no pixels, no embeddings —
    so it is safe to surface to browser clients later.

  - **face events** ``{type:'face', track_id, bbox, embedding, live_score, ts}``
    -> the matcher (Step 31). Carries the 512-d embedding, which is PII, so it is
    delivered to **in-process sinks only** — deliberately NOT the `/ws/taps` bus
    (that bus is public + typed for tap events; see events.py). This is an
    intentional deviation from the roadmap's "publish on the bus" wording.

Recognition runs **once per new track** (stable IoU track IDs), not per frame — the
throughput win and the "in/out of frame" semantics both come from that.

Fail-open: enabling perception (PERCEPTION_ENABLED) makes it the camera owner; while
it is down / not yet correlating, `/tap` logs card-only `unverified` (never silently
`present`) — see main.py and design-notes §4 (camera-dead degraded mode).
"""

import os
import time

from . import face, liveness


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


PERCEPTION_ENABLED = _bool("PERCEPTION_ENABLED", "false")
# None -> face.CAMERA_INDEX. Set to a video-file path (or image-sequence pattern)
# to run the pipeline offline against recorded footage — the acceptance path.
PERCEPTION_SOURCE = os.environ.get("PERCEPTION_SOURCE") or None
TRACK_IOU_THRESH = float(os.environ.get("TRACK_IOU_THRESH", "0.3"))
TRACK_MAX_MISSES = int(os.environ.get("TRACK_MAX_MISSES", "15"))
PERCEPTION_FPS = float(os.environ.get("PERCEPTION_FPS", "15"))  # loop-rate cap
# How often a still-visible, already-recognized track re-publishes its (cached,
# not recomputed) face event. Keeps a lingering face inside the matcher's
# ASSOC_WINDOW_SEC association window without paying recognition cost again.
FACE_REFRESH_SEC = float(os.environ.get("FACE_REFRESH_SEC", "2.0"))
# Consecutive failed reads (~0.1s apart) tolerated before a live camera is given up on.
CAMERA_MAX_MISSES = int(os.environ.get("CAMERA_MAX_MISSES", "600"))


def enabled() -> bool:
    return PERCEPTION_ENABLED


# --- In-process fan-out (matcher + viewer subscribe here) ---

_frame_sinks = []
_face_sinks = []


def on_frame(cb) -> None:
    """Register a callback for frame events. Callback receives (frame, event_dict)
    where frame is the BGR numpy array and event_dict has type/ts/tracks."""
    _frame_sinks.append(cb)


def on_face(cb) -> None:
    _face_sinks.append(cb)


def _emit(sinks, *args) -> None:
    for cb in list(sinks):
        try:
            cb(*args)
        except Exception as e:  # a bad sink must never stall the camera loop
            print(f"[perception] sink error: {e}")


# --- IoU face tracking (ByteTrack-lite: greedy IoU association) ---


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class _Track:
    __slots__ = ("id", "bbox", "misses", "recognized", "embedding", "live_score", "is_live", "last_face_ts")

    def __init__(self, tid: int, bbox):
        self.id = tid
        self.bbox = bbox
        self.misses = 0
        self.recognized = False
        self.embedding = None
        self.live_score = None
        self.is_live = None
        self.last_face_ts = None


class FaceTracker:
    """Assigns stable integer IDs to faces across frames by greedy IoU matching.
    A track survives `max_misses` frames without a match before it is dropped."""

    def __init__(self, iou_thresh: float = TRACK_IOU_THRESH, max_misses: int = TRACK_MAX_MISSES):
        self.iou_thresh = iou_thresh
        self.max_misses = max_misses
        self._tracks: dict[int, _Track] = {}
        self._next = 1

    def update(self, dets):
        """Advance the tracker by one frame. `dets` is a list of face.Detection.
        Returns [(track, detection, is_new), ...] for every live track this frame."""
        used = set()
        assigned: dict[int, int] = {}
        for tid, tr in self._tracks.items():
            best_j, best_iou = -1, self.iou_thresh
            for j, d in enumerate(dets):
                if j in used:
                    continue
                v = _iou(tr.bbox, d.bbox)
                if v >= best_iou:
                    best_iou, best_j = v, j
            if best_j >= 0:
                assigned[tid] = best_j
                used.add(best_j)

        results = []
        for tid, tr in list(self._tracks.items()):
            if tid in assigned:
                d = dets[assigned[tid]]
                tr.bbox = d.bbox
                tr.misses = 0
                results.append((tr, d, False))
            else:
                tr.misses += 1
                if tr.misses > self.max_misses:
                    del self._tracks[tid]

        for j, d in enumerate(dets):
            if j in used:
                continue
            tr = _Track(self._next, d.bbox)
            self._next += 1
            self._tracks[tr.id] = tr
            results.append((tr, d, True))
        return results


def _usable(bbox) -> bool:
    x1, y1, x2, y2 = bbox
    return min(x2 - x1, y2 - y1) >= face.MIN_FACE_PX


def _face_event(tr: _Track, det, ts: float) -> dict:
    return {
        "type": "face",
        "track_id": tr.id,
        "bbox": list(det.bbox),
        "embedding": tr.embedding,
        "live_score": tr.live_score,
        "is_live": tr.is_live,
        "ts": ts,
    }


def process_frame(frame, tracker: FaceTracker) -> list:
    """Detect + track one frame, recognize any newly-usable track once, and emit
    the frame (boxes) + face (embedding) events. Returns the tracker's updates."""
    dets = face.detect(frame)
    ts = time.time()
    updates = tracker.update(dets)

    for tr, det, _is_new in updates:
        if not tr.recognized and _usable(det.bbox):
            # Recognize once, the first frame a track is large enough to be usable.
            tr.embedding = face.embed(frame, det)
            tr.recognized = True
            tr.live_score = tr.is_live = None
            if liveness.enabled():
                tr.live_score, tr.is_live = liveness.assess(frame, det.bbox)
            tr.last_face_ts = ts
            _emit(_face_sinks, _face_event(tr, det, ts))
        elif tr.recognized and ts - tr.last_face_ts >= FACE_REFRESH_SEC:
            # Still visible: re-publish the cached embedding under a fresh
            # timestamp so a tap that lands after the one-shot recognition (but
            # while the person is still standing there) can still claim it —
            # without re-running the ~360ms recognition cost every frame.
            tr.last_face_ts = ts
            _emit(_face_sinks, _face_event(tr, det, ts))

    _emit(
        _frame_sinks,
        frame,
        {
            "type": "frame",
            "ts": ts,
            "tracks": [
                {"track_id": tr.id, "bbox": list(tr.bbox), "recognized": tr.recognized}
                for tr, _, _ in updates
            ],
        },
    )
    return updates


def run(frames, tracker: FaceTracker | None = None, max_frames: int | None = None) -> FaceTracker:
    """Consume an iterable of BGR frames through the pipeline. Decoupled from the
    camera so tests / offline runs can feed a video file or a synthetic sequence."""
    tracker = tracker or FaceTracker()
    n = 0
    for frame in frames:
        process_frame(frame, tracker)
        n += 1
        if max_frames is not None and n >= max_frames:
            break
    return tracker


def _camera_frames():
    """Yield frames from the owned camera / video source until EOF or error."""
    cap = face.open_capture(PERCEPTION_SOURCE)
    if not cap.isOpened():
        print("[perception] camera/source not available — perception idle")
        return
    # A live camera needs a moment before it delivers frames (AVFoundation on macOS
    # returns ok=False for the first reads while the capture session starts), and can
    # hiccup later. A video file, by contrast, means EOF the first time read() fails.
    is_live = PERCEPTION_SOURCE is None or str(PERCEPTION_SOURCE).isdigit()
    if is_live:
        for _ in range(face.CAMERA_WARMUP_FRAMES):
            cap.read()
    delay = 1.0 / PERCEPTION_FPS if PERCEPTION_FPS > 0 else 0.0
    misses = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                if not is_live:
                    break  # EOF (video file)
                misses += 1
                if misses == 1 or misses % 100 == 0:
                    print(f"[perception] no frame from camera (x{misses}) — retrying")
                if misses > CAMERA_MAX_MISSES:
                    print("[perception] camera stopped delivering frames — perception idle")
                    break
                time.sleep(0.1)
                continue
            misses = 0
            yield frame
            if delay:
                time.sleep(delay)
    finally:
        cap.release()


def main():
    print(
        f"[perception] starting (single camera owner) source="
        f"{PERCEPTION_SOURCE if PERCEPTION_SOURCE is not None else face.camera_index()} "
        f"iou={TRACK_IOU_THRESH} max_misses={TRACK_MAX_MISSES} fps={PERCEPTION_FPS}"
    )
    run(_camera_frames())
    print("[perception] source ended")


if __name__ == "__main__":
    main()
