"""Enroll a student's face reference (Step 6; core extracted in Step 33).

Averages 3-5 shots into one re-normalized 512-d embedding stored on students.

    python -m backend.enroll S001 --images a.jpg b.jpg c.jpg
    python -m backend.enroll S001 --capture 5

The reusable core (`embeddings_from_frames`, `enroll_student`) is I/O-free of the
CLI so the in-app register wizard (Step 35) can share it with decoded uploads.
"""

import argparse
import os
import sys

import numpy as np

from . import db, face, privacy

# Similarity at/above which a new enrollment is flagged as a possible duplicate of an
# existing student (Step 33). Defaults to the 1:1 match threshold.
DUP_ENROLL_THRESHOLD = float(os.environ.get("DUP_ENROLL_THRESHOLD", str(face.FACE_THRESHOLD)))
# Re-enrollment reminder window (Step 33); 0 = disabled.
REENROLL_AFTER_DAYS = int(os.environ.get("REENROLL_AFTER_DAYS", "0"))


# --- Shared enroll core (reused by the register wizard, Step 35) ---


def embeddings_from_frames(frames):
    """frames: iterable of BGR ndarrays -> list of usable 512-d embeddings
    (frames with no face clearing MIN_FACE_PX are skipped)."""
    out = []
    for img in frames:
        if img is None:
            continue
        emb = face.encode_image(img)
        if emb is not None:
            out.append(emb)
    return out


def average_reference(embs):
    """Average + re-normalize a list of embeddings to one unit-length reference.
    Returns None on empty input or a degenerate (zero-norm) average."""
    if not embs:
        return None
    mean = np.mean(np.stack(embs), axis=0)
    norm = float(np.linalg.norm(mean))
    if norm == 0.0:
        return None
    return (mean / norm).astype(np.float32)


def enroll_student(student_id, embs, actor="cli"):
    """Average `embs` into one reference and persist it on the student (with model
    provenance). Returns {"used": n, "duplicate": <nearest other student or None>}.
    Enforces the consent gate (Step 20), runs duplicate detection (Step 33), and
    writes an audit entry. Raises ValueError on no usable faces / degenerate average /
    consent refused; db.set_face_embedding raises if unknown."""
    student = db.get_student(student_id)
    if not privacy.enroll_allowed(student):
        raise ValueError(
            f"face consent not granted for {student_id} and FACE_CONSENT_REQUIRED is on; "
            f"grant consent first (enroll --consent, or POST /api/students/{student_id}/consent)"
        )
    ref = average_reference(embs)
    if ref is None:
        raise ValueError("no usable faces or degenerate averaged embedding")
    # Duplicate-enrollment detection (Step 33): warn (don't block) if this face already
    # exists under another student — could be a real dup or a legit re-enroll.
    dup = db.find_duplicate(ref, DUP_ENROLL_THRESHOLD, exclude_student_id=student_id)
    db.set_face_embedding(student_id, ref, embed_model=face.MODEL_NAME)
    try:
        detail = f"{len(embs)} shot(s), {face.MODEL_NAME}"
        if dup:
            detail += f"; dup?~{dup['student_id']}@{dup['similarity']:.3f}"
        db.insert_audit(actor, "enroll", student_id, detail=detail)
    except Exception as e:
        print(f"audit write failed (non-fatal): {e}")
    return {"used": len(embs), "duplicate": dup}


# --- CLI ---


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
        probe = face.capture_probe()  # Probe(frame, bbox, embedding) or None
        if probe is None:
            print("    no usable face — shot skipped")
            continue
        embs.append(probe.embedding)  # Step 33 fix: use the embedding, not the tuple
        print("    ok")
    return embs


def main():
    ap = argparse.ArgumentParser(description="Enroll a student's face reference.")
    ap.add_argument("student_id")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--images", nargs="+", metavar="PATH", help="reference image files")
    g.add_argument("--capture", type=int, metavar="N", help="capture N shots from the webcam")
    ap.add_argument(
        "--consent",
        action="store_true",
        help="record biometric consent for this student before enrolling",
    )
    args = ap.parse_args()

    if args.consent:
        db.set_consent(args.student_id, True)
        try:
            db.insert_audit("cli", "consent", args.student_id, detail="granted")
        except Exception as e:
            print(f"audit write failed (non-fatal): {e}")
        print(f"recorded consent for {args.student_id}")

    embs = _from_images(args.images) if args.images else _from_capture(args.capture)

    if not embs:
        print("no usable faces; aborting", file=sys.stderr)
        sys.exit(1)
    if len(embs) < 3:
        print(f"warning: only {len(embs)} usable shot(s); 3+ recommended for accuracy")

    try:
        result = enroll_student(args.student_id, embs)
    except ValueError as e:
        print(f"{e}; aborting", file=sys.stderr)
        sys.exit(1)
    if result["duplicate"]:
        d = result["duplicate"]
        print(
            f"WARNING: this face closely matches existing student {d['student_id']} "
            f"(similarity {d['similarity']:.3f}) — possible duplicate enrollment"
        )
    print(f"enrolled {args.student_id} from {result['used']} shot(s)")


if __name__ == "__main__":
    main()
