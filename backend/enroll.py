"""Enroll a student's face reference (Step 6).

Averages 3-5 shots into one re-normalized 512-d embedding stored on students.

    python -m backend.enroll S001 --images a.jpg b.jpg c.jpg
    python -m backend.enroll S001 --capture 5
"""

import argparse
import sys

import numpy as np

from . import db, face


def _from_images(paths):
    import cv2

    embs = []
    for p in paths:
        img = cv2.imread(p)
        if img is None:
            print(f"  skip {p}: cannot read file")
            continue
        emb = face.encode_image(img)
        if emb is None:
            print(f"  skip {p}: no usable face (need >= {face.MIN_FACE_PX}px)")
            continue
        embs.append(emb)
        print(f"  ok   {p}")
    return embs


def _from_capture(n):
    embs = []
    for i in range(n):
        input(f"  shot {i + 1}/{n}: face the camera, press Enter... ")
        emb = face.capture_probe()
        if emb is None:
            print("    no usable face — shot skipped")
            continue
        embs.append(emb)
        print("    ok")
    return embs


def main():
    ap = argparse.ArgumentParser(description="Enroll a student's face reference.")
    ap.add_argument("student_id")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--images", nargs="+", metavar="PATH", help="reference image files")
    g.add_argument("--capture", type=int, metavar="N", help="capture N shots from the webcam")
    args = ap.parse_args()

    embs = _from_images(args.images) if args.images else _from_capture(args.capture)

    if not embs:
        print("no usable faces; aborting", file=sys.stderr)
        sys.exit(1)
    if len(embs) < 3:
        print(f"warning: only {len(embs)} usable shot(s); 3+ recommended for accuracy")

    mean = np.mean(np.stack(embs), axis=0)
    norm = float(np.linalg.norm(mean))
    if norm == 0.0:
        print("degenerate averaged embedding; aborting", file=sys.stderr)
        sys.exit(1)
    mean = (mean / norm).astype(np.float32)  # re-normalize to unit length

    db.set_face_embedding(args.student_id, mean)
    print(f"enrolled {args.student_id} from {len(embs)} shot(s)")


if __name__ == "__main__":
    main()
