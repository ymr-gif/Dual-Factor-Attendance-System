"""Live camera diagnostic UI (setup aid, not part of the tap flow).

Shows what the capture pipeline sees each frame: detected face box, its size vs the
MIN_FACE_PX gate, the live/spoof score, and (optionally) the match score against an
enrolled student. Use it to aim/light the kiosk camera before tapping.

    python -m backend.preview                # detection + liveness
    python -m backend.preview --match S001   # also show cosine vs S001's reference

Press q (or Esc) to quit. NOTE: this holds the webcam while open — only one process can,
so a /tap during preview will fail to capture. Close this before live tapping.
"""

import argparse
import time

import numpy as np

from . import face, liveness

GREEN = (0, 200, 0)
RED = (0, 0, 255)
ORANGE = (0, 165, 255)
WHITE = (255, 255, 255)


def _load_reference(student_id):
    import psycopg2.extras

    from . import db

    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT face_embedding FROM students WHERE student_id = %s", (student_id,))
            row = cur.fetchone()
    if not row or row["face_embedding"] is None:
        return None
    return db.embedding_to_numpy(row["face_embedding"])


def main():
    import cv2

    ap = argparse.ArgumentParser(description="Live camera diagnostic preview.")
    ap.add_argument("--match", metavar="STUDENT_ID", help="show cosine vs this student's reference")
    ap.add_argument("--every", type=int, default=3, help="run liveness every Nth frame (CPU)")
    args = ap.parse_args()

    ref = _load_reference(args.match) if args.match else None
    if args.match and ref is None:
        print(f"note: {args.match} has no enrolled face_embedding — match will be skipped")

    cam_idx = face.camera_index()
    cap = cv2.VideoCapture(cam_idx)
    if not cap.isOpened():
        print(f"cannot open camera index {cam_idx}")
        return

    face.get_app()  # warm the model
    win = "nfc-scan camera preview"
    t_prev, fps = time.time(), 0.0
    frame_i = 0
    last_live = (None, None)  # cached (score, is_live) between throttled liveness runs
    last_match = None  # cached cosine between throttled recognition runs

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frame_i += 1
            dets = face.detect(frame)  # detection only — cheap, every frame
            usable = face.largest_usable(dets)
            throttled = frame_i % max(args.every, 1) == 0

            # every detected face: box + size, colored by whether it clears the gate
            for d in dets:
                x1, y1, x2, y2 = d.bbox
                side = min(x2 - x1, y2 - y1)
                is_usable = d is usable
                color = GREEN if is_usable else ORANGE
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                tag = f"{x2 - x1}x{y2 - y1}px"
                if side < face.MIN_FACE_PX:
                    tag += " TOO SMALL"
                cv2.putText(frame, tag, (x1, max(y1 - 8, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # liveness + match on the usable face — heavy, so throttled
            if usable is not None:
                x1, y1, x2, y2 = usable.bbox
                if liveness.enabled() and throttled:
                    last_live = liveness.assess(frame, usable.bbox)
                score, is_live = last_live
                if score is not None:
                    cv2.putText(frame, f"{'LIVE' if is_live else 'SPOOF'} {score:.2f}",
                                (x1, y2 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                GREEN if is_live else RED, 2)
                if ref is not None:
                    if throttled:
                        last_match = face.cosine(face.embed(frame, usable), ref)
                    if last_match is not None:
                        ok_m = last_match >= face.FACE_THRESHOLD
                        cv2.putText(frame, f"{'MATCH' if ok_m else 'NO MATCH'} {last_match:.2f}",
                                    (x1, y2 + 46), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                    GREEN if ok_m else RED, 2)

            now = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - t_prev, 1e-6))
            t_prev = now
            head = (f"cam{cam_idx}  faces:{len(dets)}  "
                    f"MIN_FACE_PX:{face.MIN_FACE_PX}  FACE_THR:{face.FACE_THRESHOLD}  "
                    f"{fps:4.1f}fps")
            cv2.putText(frame, head, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
            cv2.putText(frame, "q = quit", (8, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

            cv2.imshow(win, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
