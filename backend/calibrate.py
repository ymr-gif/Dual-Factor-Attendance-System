"""Threshold calibration helper (read-only).

Prints the distribution of logged scores so a threshold can be set from measured data
instead of a guess. No writes.

    python -m backend.calibrate                      # face_score (default)
    python -m backend.calibrate --metric liveness    # liveness_score
    python -m backend.calibrate --metric liveness --days 7
"""

import argparse

import numpy as np

from . import db, face, liveness

METRICS = {
    # metric -> (score column, verdict column, current threshold, verdict labels)
    "face": ("face_score", "face_match", face.FACE_THRESHOLD, ("match", "mismatch")),
    "liveness": ("liveness_score", "liveness_pass", liveness.LIVENESS_THRESHOLD, ("live", "spoof")),
}


def _report(rows, score_col, verdict_col, threshold, labels):
    scores = np.array([r[0] for r in rows], dtype=np.float32)
    pos = sum(1 for r in rows if r[1] is True)
    neg = sum(1 for r in rows if r[1] is False)

    print(f"scored taps: {len(scores)}  ({labels[0]}={pos}, {labels[1]}={neg})")
    print(f"min={scores.min():.3f}  mean={scores.mean():.3f}  max={scores.max():.3f}")
    print("percentiles:")
    for p in (1, 5, 10, 25, 50, 75, 90, 95, 99):
        print(f"  p{p:<2} = {np.percentile(scores, p):.3f}")

    print(f"histogram ({score_col} bucket : count):")
    hist, edges = np.histogram(scores, bins=10, range=(0.0, 1.0))
    for i, c in enumerate(hist):
        print(f"  {edges[i]:.1f}-{edges[i + 1]:.1f} | {'#' * int(c)} {int(c)}")

    thr = "unset (argmax verdict)" if threshold is None else threshold
    print(f"\ncurrent threshold = {thr}")
    print(f"Aim below the genuine ({labels[0]}) cluster's low tail, above the {labels[1]} scores.")


def main():
    ap = argparse.ArgumentParser(description="Show logged score distribution.")
    ap.add_argument("--metric", choices=sorted(METRICS), default="face")
    ap.add_argument("--days", type=int, default=None, help="only taps in the last N days")
    args = ap.parse_args()

    score_col, verdict_col, threshold, labels = METRICS[args.metric]
    sql = f"SELECT {score_col}, {verdict_col} FROM attendance_logs WHERE {score_col} IS NOT NULL"
    params = []
    if args.days:
        sql += " AND ts >= now() - make_interval(days => %s)"
        params.append(args.days)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        print(f"no {args.metric} scores yet — tap a few students first")
        return

    _report(rows, score_col, verdict_col, threshold, labels)


if __name__ == "__main__":
    main()
