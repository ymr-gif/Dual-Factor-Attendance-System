"""Passive liveness / anti-spoofing (Step 7). MiniFASNet ensemble via onnxruntime.

Single-frame anti-spoof: catches printed-photo / phone-screen attacks that pass the
face match (a photo of the enrolled student still matches the 1:1 check). Runs two
MiniFASNet models (V2 @ scale 2.7, V1SE @ scale 4.0) and sums their softmax — the
official Silent-Face-Anti-Spoofing approach (Apache-2.0, minivision-ai).

Heavy work (onnxruntime, cv2) is lazy so importing this module stays cheap.
"""

import os

import numpy as np

_HERE = os.path.dirname(__file__)

LIVENESS_ENABLED = os.environ.get("LIVENESS_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
LIVENESS_MODEL_DIR = os.environ.get(
    "LIVENESS_MODEL_DIR", os.path.join(_HERE, "models", "anti_spoof")
)
# Unset -> verdict by the model's native argmax (live vs print/replay).
# Set -> is_live = p_live >= LIVENESS_THRESHOLD. Leave unset until calibrated.
_thr = os.environ.get("LIVENESS_THRESHOLD")
LIVENESS_THRESHOLD = float(_thr) if _thr not in (None, "") else None

# (filename, crop scale) — each model was trained on its own bbox crop scale.
MODELS = [
    ("2.7_80x80_MiniFASNetV2.onnx", 2.7),
    ("4_0_0_80x80_MiniFASNetV1SE.onnx", 4.0),
]
_INPUT_SIZE = 80
_LIVE_IDX = 1  # output softmax classes: [live, print, replay]

_sessions = None


def enabled() -> bool:
    return LIVENESS_ENABLED


def calibrated() -> bool:
    """True once LIVENESS_THRESHOLD is set. Until then the model's argmax verdict is
    untrusted (⚠ not calibrated against real spoofs) and must not decide a tap —
    callers should treat is_live as advisory and still log the score for calibration."""
    return LIVENESS_THRESHOLD is not None


def get_sessions():
    """Lazy, cached list of (onnxruntime session, scale). Raises if a model is missing.

    Honors the shared USE_GPU switch (via face.gpu_runtime) so one env var drives both
    face and liveness onto CPU or the GPU, with automatic CPU fallback.
    """
    global _sessions
    if _sessions is None:
        import onnxruntime as ort

        from .face import gpu_runtime

        _, providers = gpu_runtime()
        sess = []
        for name, scale in MODELS:
            path = os.path.join(LIVENESS_MODEL_DIR, name)
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"liveness model missing: {path} — run `python -m backend.fetch_liveness_models`"
                )
            sess.append((ort.InferenceSession(path, providers=providers), scale))
        _sessions = sess
    return _sessions


def _get_new_box(src_w, src_h, bbox_xywh, scale):
    """Silent-Face crop box: enlarge bbox by `scale` around its center, clamp to image."""
    x, y, box_w, box_h = bbox_xywh
    scale = min((src_h - 1) / box_h, min((src_w - 1) / box_w, scale))
    new_w = box_w * scale
    new_h = box_h * scale
    cx = box_w / 2 + x
    cy = box_h / 2 + y
    x1 = cx - new_w / 2
    y1 = cy - new_h / 2
    x2 = cx + new_w / 2
    y2 = cy + new_h / 2
    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > src_w - 1:
        x1 -= x2 - (src_w - 1)
        x2 = src_w - 1
    if y2 > src_h - 1:
        y1 -= y2 - (src_h - 1)
        y2 = src_h - 1
    return int(x1), int(y1), int(x2), int(y2)


def _crop(frame, bbox_xywh, scale):
    """Scaled crop around the face, resized to 80x80 (BGR)."""
    import cv2

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = _get_new_box(w, h, bbox_xywh, scale)
    crop = frame[y1:y2, x1:x2]
    return cv2.resize(crop, (_INPUT_SIZE, _INPUT_SIZE))


def _softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / e.sum()


def assess(frame, bbox):
    """Score liveness of the face at `bbox` in `frame`.

    bbox: InsightFace [x1,y1,x2,y2]. Returns (score, is_live):
      score  = p_live in [0,1], ensembled over both models
      is_live = argmax verdict (or threshold when LIVENESS_THRESHOLD is set)
    Fail-open: any error / missing model -> (None, None) so the tap still logs.
    """
    try:
        x1, y1, x2, y2 = bbox
        bbox_xywh = (x1, y1, x2 - x1, y2 - y1)
        combined = np.zeros(3, dtype=np.float64)
        for sess, scale in get_sessions():
            img = _crop(frame, bbox_xywh, scale)
            blob = (img.astype(np.float32) / 255.0).transpose(2, 0, 1)[None, ...]  # NCHW
            out = sess.run(None, {sess.get_inputs()[0].name: blob})[0][0]
            combined += _softmax(out)
        combined /= len(MODELS)
        score = float(combined[_LIVE_IDX])
        if LIVENESS_THRESHOLD is None:
            is_live = bool(int(np.argmax(combined)) == _LIVE_IDX)
        else:
            is_live = bool(score >= LIVENESS_THRESHOLD)
        return score, is_live
    except Exception as e:
        print(f"[liveness] assess failed, failing open: {e}")
        return None, None
