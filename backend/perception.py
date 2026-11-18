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
throughput win and the "in/out of frame" semantics both come from that. A track that
stays visible re-publishes its face event every `FACE_REFRESH_SEC`, and is recognized
again first if it lost its face for a frame or more since the last recognition, or if
no frame was processed for `TRACK_STALE_SEC`.

Limit: tracks are matched by box overlap only. A person who takes over a track with no
missed frame keeps the previous person's cached identity until that track next loses
its face.

Fail-open: enabling perception (PERCEPTION_ENABLED) makes it the camera owner; while
it is down / not yet correlating, `/tap` logs card-only `unverified` (never silently
`present`) — see main.py and design-notes §4 (camera-dead degraded mode).
"""

import os
import threading
import time
from time import perf_counter  # timings in the log; tests replace `time` itself

from . import face, liveness


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


PERCEPTION_ENABLED = _bool("PERCEPTION_ENABLED", "false")
# None -> the camera face.camera_index() selects. Set to a video-file path (or image-sequence pattern)
# to run the pipeline offline against recorded footage — the acceptance path.
PERCEPTION_SOURCE = os.environ.get("PERCEPTION_SOURCE") or None
TRACK_IOU_THRESH = float(os.environ.get("TRACK_IOU_THRESH", "0.3"))
TRACK_MAX_MISSES = int(os.environ.get("TRACK_MAX_MISSES", "15"))
PERCEPTION_FPS = float(os.environ.get("PERCEPTION_FPS", "15"))  # loop-rate cap
# How often a still-visible, already-recognized track publishes a new face event, so
# that a tap which comes after the first recognition can still claim the face. The
# matcher keeps a face event for ASSOC_WINDOW_SEC + 1 s and judges a tap
# ASSOC_WINDOW_SEC after it arrived, so a tap can claim an event published up to about
# 1 s before it, or any time in the window after it. With a refresh longer than that,
# a person who taps and leaves before the next refresh gets no_face.
# An unbroken track re-publishes its cached embedding and liveness verdict, so a
# refresh costs no recognition. A track that missed a frame since it was last
# recognized may hold another person, and is recognized again instead.
FACE_REFRESH_SEC = float(os.environ.get("FACE_REFRESH_SEC", "2.0"))
# A pause this long with no processed frame (failed camera reads, a stalled loop) counts
# as a missed frame for every track: the tracker did not see who came and went.
TRACK_STALE_SEC = float(os.environ.get("TRACK_STALE_SEC", "1.0"))
# Consecutive failed reads (~0.1s apart) tolerated before a live camera is given up on.
CAMERA_MAX_MISSES = int(os.environ.get("CAMERA_MAX_MISSES", "100"))
# Seconds between attempts to reopen a live camera that stopped or was never there.
CAMERA_RETRY_SEC = float(os.environ.get("CAMERA_RETRY_SEC", "5"))
# Seconds between the speed lines in the log (frames per second, detection time,
# camera frames skipped). 0 turns them off.
PERCEPTION_STATS_SEC = float(os.environ.get("PERCEPTION_STATS_SEC", "30"))


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
    __slots__ = (
        "id", "bbox", "misses", "reacquired", "recognized", "embedding", "live_score",
        "is_live", "last_face_ts",
    )

    def __init__(self, tid: int, bbox):
        self.id = tid
        self.bbox = bbox
        self.misses = 0
        # True once the track was matched again after one or more missed frames, until
        # it is next recognized: the face in it now may not be the one recognized.
        self.reacquired = False
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
        # When process_frame last finished a frame. Measured from the end of a frame,
        # so time spent recognizing inside a frame is not mistaken for a pause.
        self.last_done_ts = None

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
                if tr.misses:
                    tr.reacquired = True
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


def _recognize(tr: _Track, frame, det) -> None:
    """Measure the face now in this track: embedding, and liveness when enabled.
    The track is updated only once both are in hand, so a failure part-way leaves
    it as it was and still due for recognition."""
    t0 = perf_counter()
    embedding = face.embed(frame, det)
    t1 = perf_counter()
    live_score = is_live = None
    if liveness.enabled():
        live_score, is_live = liveness.assess(frame, det.bbox)
    t2 = perf_counter()
    again = tr.recognized
    tr.embedding = embedding
    tr.live_score, tr.is_live = live_score, is_live
    tr.recognized = True
    tr.reacquired = False
    x1, _y1, x2, _y2 = det.bbox
    live = "off" if live_score is None else f"{live_score:.2f} ({'live' if is_live else 'not live'})"
    print(f"[perception] track {tr.id}: face {int(x2 - x1)} px {'re-' if again else ''}recognized "
          f"in {(t1 - t0) * 1000:.0f} ms, liveness {live} in {(t2 - t1) * 1000:.0f} ms")


class _Stats:
    """Pipeline speed for the log: frames processed, time spent detecting, and camera
    frames skipped because the pipeline was busy. One line every PERCEPTION_STATS_SEC."""

    def __init__(self):
        self._reset(perf_counter())
        self.skipped = 0

    def _reset(self, now):
        self.since = now
        self.frames = 0
        self.detect_sec = 0.0

    def detected(self, sec: float) -> None:
        self.frames += 1
        self.detect_sec += sec
        now = perf_counter()
        span = now - self.since
        if PERCEPTION_STATS_SEC <= 0 or span < PERCEPTION_STATS_SEC:
            return
        skipped, self.skipped = self.skipped, 0
        print(f"[perception] {self.frames / span:.1f} fps, detection "
              f"{self.detect_sec / self.frames * 1000:.0f} ms a frame, "
              f"{skipped} camera frames skipped (last {span:.0f} s)")
        self._reset(now)


_stats = _Stats()


def process_frame(frame, tracker: FaceTracker) -> list:
    """Detect + track one frame, recognize any newly-usable track, refresh the
    tracks that are due, and emit the frame (boxes) + face (embedding) events.
    Returns the tracker's updates."""
    t0 = perf_counter()
    dets = face.detect(frame)
    _stats.detected(perf_counter() - t0)
    ts = time.time()
    # No frame was processed for longer than TRACK_STALE_SEC: the tracker counted no
    # missed frame, but whoever is in a track now may not be who was recognized.
    stalled = tracker.last_done_ts is not None and ts - tracker.last_done_ts > TRACK_STALE_SEC
    updates = tracker.update(dets)
    if stalled:
        for tr, _det, _is_new in updates:
            tr.reacquired = True

    for tr, det, _is_new in updates:
        if not _usable(det.bbox):
            continue
        if not tr.recognized:
            # Recognize once, the first frame a track is large enough to be usable.
            _recognize(tr, frame, det)
            tr.last_face_ts = ts
            _emit(_face_sinks, _face_event(tr, det, ts))
        elif ts - tr.last_face_ts >= FACE_REFRESH_SEC:
            # Still visible: publish again under a fresh timestamp so a tap that
            # lands after the first recognition (but while the person is still
            # standing there) can still claim it. An unbroken track re-publishes
            # its cached embedding, so recognition is not paid for again. A track
            # that lost its face for a frame or more can have passed to the next
            # person standing in the same spot; replaying the cache would then
            # accept the first person's card, so that track is recognized again.
            if tr.reacquired:
                _recognize(tr, frame, det)
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
    tracker.last_done_ts = time.time()
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


def _is_live_source() -> bool:
    """A camera (unset, an index, or a /dev/ path), as opposed to a video file."""
    src = PERCEPTION_SOURCE
    return src is None or str(src).isdigit() or str(src).startswith("/dev/")


def run_forever(sleep=time.sleep, max_rounds: int | None = None):
    """Camera-owner loop (PC-033). Runs the pipeline on the camera; when a live camera
    stops delivering frames or is not there, closes it and reopens it every
    CAMERA_RETRY_SEC, so an unplugged camera works again once plugged back without a
    backend restart. The camera is re-resolved on each try, so another USB socket is
    fine. A video file runs once."""
    live = _is_live_source()
    rounds = 0
    waiting = False
    next_id = 1
    while True:
        # A fresh tracker per round drops the faces from before the outage, but its IDs
        # carry on from the last round: the matcher remembers judged track IDs, so a
        # reused ID would let a new face pass as one already handled.
        tracker = FaceTracker()
        tracker._next = next_id
        try:
            run(_camera_frames(), tracker=tracker)
        except Exception as e:
            print(f"[perception] pipeline error: {e}")
        next_id = tracker._next
        rounds += 1
        if not live or (max_rounds is not None and rounds >= max_rounds):
            return
        if tracker.last_done_ts:
            waiting = False  # frames came through this round: announce the next outage
        if not waiting:
            print(f"[perception] no camera — trying again every {CAMERA_RETRY_SEC:g} s")
            waiting = True
        sleep(CAMERA_RETRY_SEC)


class _Newest:
    """Reads a live camera on its own thread and keeps only its newest read.

    A camera keeps capturing while a frame is processed. Read one by one, the frames
    queue up in the driver, and on a slow machine (the MacBook Air at about 5 fps) the
    pipeline works on what the camera saw a while ago, so a tap is judged against an
    old picture. Here a read that was not taken in time is replaced by the next one,
    so read() always returns what the camera sees now. Failed reads are passed on the
    same way, so the caller's miss counting is unchanged."""

    def __init__(self, cap):
        self._cap = cap
        self._cond = threading.Condition()
        self._latest = None  # (ok, frame) not yet taken
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="camera-reader", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop:
            ok, frame = self._cap.read()
            good = ok and frame is not None
            with self._cond:
                if self._latest is not None and self._latest[0]:
                    _stats.skipped += 1
                self._latest = (good, frame if good else None)
                self._cond.notify()
            if not good:
                time.sleep(0.1)

    def read(self):
        with self._cond:
            while self._latest is None:
                self._cond.wait()
            got, self._latest = self._latest, None
        return got

    def close(self):
        self._stop = True
        self._thread.join(timeout=2.0)  # a read in progress ends within a frame


def _camera_frames():
    """Yield frames from the owned camera / video source until EOF or error."""
    cap = face.open_capture(PERCEPTION_SOURCE)
    if not cap.isOpened():
        if not _is_live_source():
            print("[perception] video source not available — perception idle")
        return  # a live camera: run_forever says so once and tries again
    # A live camera needs a moment before it delivers frames (AVFoundation on macOS
    # returns ok=False for the first reads while the capture session starts), and can
    # hiccup later. A video file, by contrast, means EOF the first time read() fails.
    is_live = _is_live_source()
    if is_live:
        for _ in range(face.CAMERA_WARMUP_FRAMES):
            cap.read()
    # A live camera is read through _Newest so no frame waits; a video file is read
    # frame by frame so offline runs see every frame.
    source = _Newest(cap) if is_live else cap
    # PERCEPTION_FPS caps the loop rate; only the part of a frame's budget that
    # processing did not use is slept, so a slow machine does not wait on top.
    budget = 1.0 / PERCEPTION_FPS if PERCEPTION_FPS > 0 else 0.0
    misses = 0
    try:
        while True:
            ok, frame = source.read()
            if not ok or frame is None:
                if not is_live:
                    break  # EOF (video file)
                misses += 1
                if misses == 1 or misses % 100 == 0:
                    print(f"[perception] no frame from camera (x{misses}) — retrying")
                if misses > CAMERA_MAX_MISSES:
                    print("[perception] camera stopped delivering frames — closing it")
                    break
                continue  # _Newest already waited 0.1 s after the failed read
            misses = 0
            started = perf_counter()
            yield frame
            left = budget - (perf_counter() - started)
            if left > 0:
                time.sleep(left)
    finally:
        if is_live:
            source.close()
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
