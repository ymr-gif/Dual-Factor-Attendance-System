"""Download the MiniFASNet anti-spoofing ONNX weights (Step 7).

Idempotent: skips a file that already exists with the right sha256. Run once at setup:

    python -m backend.fetch_liveness_models

Weights are ONNX exports of minivision-ai/Silent-Face-Anti-Spoofing (Apache-2.0),
mirrored on the yakhyo/face-anti-spoofing GitHub release.
"""

import hashlib
import os
import sys
import urllib.request

from .liveness import LIVENESS_MODEL_DIR

# filename -> (url, sha256)
WEIGHTS = {
    "2.7_80x80_MiniFASNetV2.onnx": (
        "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx",
        "b32929adc2d9c34b9486f8c4c7bc97c1b69bc0ea9befefc380e4faae4e463907",
    ),
    "4_0_0_80x80_MiniFASNetV1SE.onnx": (
        "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx",
        "ebab7f90c7833fbccd46d3a555410e78d969db5438e169b6524be444862b3676",
    ),
}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(LIVENESS_MODEL_DIR, exist_ok=True)
    for name, (url, sha) in WEIGHTS.items():
        path = os.path.join(LIVENESS_MODEL_DIR, name)
        if os.path.exists(path) and _sha256(path) == sha:
            print(f"ok (cached)  {name}")
            continue
        print(f"downloading  {name} <- {url}")
        urllib.request.urlretrieve(url, path)
        got = _sha256(path)
        if got != sha:
            os.remove(path)
            print(f"sha256 mismatch for {name}: expected {sha}, got {got}", file=sys.stderr)
            sys.exit(1)
        print(f"ok           {name}")
    print(f"models in {LIVENESS_MODEL_DIR}")


if __name__ == "__main__":
    main()
