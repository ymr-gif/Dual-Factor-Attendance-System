"""Face verification (Step 6, 1:1). InsightFace buffalo_l ArcFace, 512-d.

Detection and recognition are split: detection is cheap (~60ms) and runs on every
frame, recognition (~350ms) is the bottleneck and runs only on the single largest
face — so cost is independent of how many students are in frame. The buffalo_l pack
is loaded with only detection+recognition (landmark/gender-age dropped).

Heavy deps (insightface, cv2) are imported lazily inside functions so importing
this module — and running with FACE_MATCH_ENABLED=false — stays cheap.
"""

import os
from collections import namedtuple

import numpy as np

# One capture per tap, reused by both face match and liveness (Step 7):
# frame = the winning BGR frame, bbox = [x1,y1,x2,y2] ints, embedding = normed 512-d.
Probe = namedtuple("Probe", "frame bbox embedding")

# Recognition model pack — stored as embedding provenance (embed_model, Step 33).
MODEL_NAME = "buffalo_l"

CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))  # explicit setting; prefer camera_index()
FACE_THRESHOLD = float(os.environ.get("FACE_THRESHOLD", "0.5"))  # conservative; calibrate from logs
CAMERA_WARMUP_FRAMES = int(os.environ.get("CAMERA_WARMUP_FRAMES", "5"))
CAMERA_PROBE_FRAMES = int(os.environ.get("CAMERA_PROBE_FRAMES", "5"))
MIN_FACE_PX = int(os.environ.get("MIN_FACE_PX", "80"))
FACE_DET_SIZE = int(os.environ.get("FACE_DET_SIZE", "320"))  # kiosk close-face; raise for far/small faces
# GPU on/off switch. Default CPU. Set USE_GPU=true once on a CUDA box (RTX 1050) —
# same code, no edits. Falls back to CPU (with a warning) if CUDA isn't available,
# so it's safe to preset before the hardware migration.
USE_GPU = os.environ.get("USE_GPU", "false").lower() in ("1", "true", "yes", "on")
FACE_MATCH_ENABLED = os.environ.get("FACE_MATCH_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

_app = None


def enabled() -> bool:
    return FACE_MATCH_ENABLED


def gpu_runtime():
    """(ctx_id, providers) honoring USE_GPU, with automatic CPU fallback.

    Shared selection logic — liveness uses the providers list too.
    """
    if USE_GPU:
        import onnxruntime as ort

        if "CUDAExecutionProvider" in ort.get_available_providers():
            return 0, ["CUDAExecutionProvider", "CPUExecutionProvider"]
        print("[face] USE_GPU=true but CUDAExecutionProvider unavailable — using CPU")
    return -1, ["CPUExecutionProvider"]


def get_app():
    """Lazy, cached InsightFace app, detection+recognition only, all cores, CPU or GPU."""
    global _app
    if _app is None:
        os.environ.setdefault("OMP_NUM_THREADS", str(os.cpu_count() or 4))
        from insightface.app import FaceAnalysis

        ctx_id, providers = gpu_runtime()
        app = FaceAnalysis(
            name=MODEL_NAME, allowed_modules=["detection", "recognition"], providers=providers
        )
        app.prepare(ctx_id=ctx_id, det_size=(FACE_DET_SIZE, FACE_DET_SIZE))
        _app = app
    return _app


# A detected face carries just what we need downstream: box, keypoints, score.
Detection = namedtuple("Detection", "bbox kps score")


def detect(img):
    """Detection only (fast). List of Detection(bbox=[x1,y1,x2,y2] ints, kps, score)."""
    bboxes, kpss = get_app().det_model.detect(img, max_num=0, metric="default")
    out = []
    for i in range(bboxes.shape[0]):
        x1, y1, x2, y2 = (int(v) for v in bboxes[i, :4])
        kps = kpss[i] if kpss is not None else None
        out.append(Detection((x1, y1, x2, y2), kps, float(bboxes[i, 4])))
    return out


def largest_usable(dets):
    """Largest detection whose smaller side clears MIN_FACE_PX, else None."""
    best, best_area = None, 0
    for d in dets:
        x1, y1, x2, y2 = d.bbox
        if min(x2 - x1, y2 - y1) < MIN_FACE_PX:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best, best_area = d, area
    return best


def embed(img, det):
    """Run recognition on a single detected face -> normed 512-d embedding."""
    from insightface.app.common import Face

    f = Face(bbox=np.asarray(det.bbox, dtype=np.float32), kps=det.kps, det_score=det.score)
    get_app().models["recognition"].get(img, f)
    return np.asarray(f.normed_embedding, dtype=np.float32)


def encode_image(img):
    """img: BGR ndarray. Normalized 512-d embedding of the largest usable face, or None."""
    det = largest_usable(detect(img))
    if det is None:
        return None
    return embed(img, det)


def camera_index() -> int:
    """The camera index to open: CAMERA_INDEX when set, else auto-selected.

    Resolved lazily rather than at import — discovery shells out to the OS, and
    every CLI that imports this module would otherwise pay for it. See
    backend/cameras.py for the selection rules.
    """
    from . import cameras

    return cameras.pick_index(CAMERA_INDEX)


def open_capture(source=None):
    """Open a cv2.VideoCapture on `source` and return it (caller owns/releases).

    `source` may be an int index, a numeric string, a device path, or a video /
    image-sequence file. Defaults to the resolved camera (see camera_index()).
    Centralizing camera opening here lets the perception service (Step 30) be the
    *single camera owner* (design-notes §3) and lets tests / the viewer feed a
    video file instead of the live cam.
    """
    import cv2

    if source is None:
        source = camera_index()
    elif isinstance(source, str) and source.isdigit():
        source = int(source)
    return cv2.VideoCapture(source)


def capture_probe():
    """Best-of-N webcam capture. `Probe(frame, bbox, embedding)` for the largest usable
    face seen, or None.

    Detection runs on every frame (cheap); recognition runs once, on the winning face
    only — so tap cost doesn't grow with the number of people in view. Returns the frame
    + bbox too so liveness reuses the exact same capture (no second camera open).

    NOTE: this opens the camera itself, so it must not run while the perception
    service (Step 30) owns it — single camera owner. When PERCEPTION_ENABLED, /tap
    stops calling this and correlation moves to the matcher (Step 31).
    """
    cap = open_capture()
    try:
        if not cap.isOpened():
            return None
        for _ in range(CAMERA_WARMUP_FRAMES):
            cap.read()
        best, best_frame, best_area = None, None, 0
        for _ in range(CAMERA_PROBE_FRAMES):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            det = largest_usable(detect(frame))
            if det is None:
                continue
            x1, y1, x2, y2 = det.bbox
            area = (x2 - x1) * (y2 - y1)
            if area > best_area:
                best, best_frame, best_area = det, frame, area
        if best is None:
            return None
        emb = embed(best_frame, best)  # recognition once, on the winner
        return Probe(frame=best_frame, bbox=best.bbox, embedding=emb)
    finally:
        cap.release()


def cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
