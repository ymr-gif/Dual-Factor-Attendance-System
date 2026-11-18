"""Threshold calibration helper (read-only).

Prints the distribution of logged scores so a threshold can be set from measured data
instead of a guess. No writes.

    python -m backend.calibrate                      # face_score (default)
    python -m backend.calibrate --metric liveness    # liveness_score
    python -m backend.calibrate --metric liveness --days 7

Two rounds (PC-025): the genuine round in one time window, the spoof round (photo,
screen) in another. Times are HH:MM today or a full date and time, on the attendance
clock (ATTENDANCE_TZ):

    python -m backend.calibrate --metric liveness --since 09:00 --until 09:20 \
        --against-since 09:25 --against-until 09:45

prints both distributions, where they overlap, and a threshold between them.
"""

import argparse
import re
from datetime import date

import numpy as np

from . import db, face, liveness

METRICS = {
    # metric -> (score column, verdict column, current threshold, verdict labels)
    "face": ("face_score", "face_match", face.FACE_THRESHOLD, ("match", "mismatch")),
    "liveness": ("liveness_score", "liveness_pass", liveness.threshold(), ("live", "spoof")),
}


def summarize(rows, threshold, labels) -> dict:
    """The distribution stats `_report` prints and the web UI's calibration panel
    reads, as plain data: count, pos/neg verdict counts, min/mean/max, percentiles,
    a 10-bucket histogram, and the threshold in force. No writes, no printing."""
    scores = np.array([r[0] for r in rows], dtype=np.float32)
    pos = sum(1 for r in rows if r[1] is True)
    neg = sum(1 for r in rows if r[1] is False)
    percentiles = {p: float(np.percentile(scores, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)}
    hist, edges = np.histogram(scores, bins=10, range=(0.0, 1.0))
    histogram = [
        {"low": float(edges[i]), "high": float(edges[i + 1]), "count": int(c)}
        for i, c in enumerate(hist)
    ]
    return {
        "count": len(scores),
        "labels": {"pos": labels[0], "neg": labels[1]},
        "pos": pos,
        "neg": neg,
        "min": float(scores.min()),
        "mean": float(scores.mean()),
        "max": float(scores.max()),
        "percentiles": percentiles,
        "histogram": histogram,
        "threshold": threshold,
    }


def _report(rows, score_col, verdict_col, threshold, labels):
    s = summarize(rows, threshold, labels)
    print(f"scored taps: {s['count']}  ({labels[0]}={s['pos']}, {labels[1]}={s['neg']})")
    print(f"min={s['min']:.3f}  mean={s['mean']:.3f}  max={s['max']:.3f}")
    print("percentiles:")
    for p, v in s["percentiles"].items():
        print(f"  p{p:<2} = {v:.3f}")

    print(f"histogram ({score_col} bucket : count):")
    for b in s["histogram"]:
        print(f"  {b['low']:.1f}-{b['high']:.1f} | {'#' * b['count']} {b['count']}")

    thr = "unset (argmax verdict)" if threshold is None else threshold
    print(f"\ncurrent threshold = {thr}")
    print(f"Aim below the genuine ({labels[0]}) cluster's low tail, above the {labels[1]} scores.")


def when(text, today=None):
    """HH:MM -> that time today; anything else is passed on as a timestamp."""
    if text is None:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}", text.strip()):
        return f"{(today or date.today()).isoformat()} {text.strip()}"
    return text.strip()


def query(score_col, verdict_col, days=None, since=None, until=None, today=None):
    """The SELECT and its parameters for one window."""
    sql = f"SELECT {score_col}, {verdict_col} FROM attendance_logs WHERE {score_col} IS NOT NULL"
    params = []
    if days:
        sql += " AND ts >= now() - make_interval(days => %s)"
        params.append(days)
    if since:
        sql += " AND ts >= %s::timestamptz"
        params.append(when(since, today))
    if until:
        sql += " AND ts < %s::timestamptz"
        params.append(when(until, today))
    return sql, params


def separation(genuine, spoof):
    """Where the genuine and spoof scores sit apart. Returns a dict: the highest spoof,
    the lowest genuine, a threshold halfway between when they do not overlap (else
    None), and the errors each side would have at that threshold, or at the point that
    makes the fewest errors when they overlap."""
    g = sorted(genuine)
    s = sorted(spoof)
    out = {"spoof_max": s[-1], "genuine_min": g[0], "threshold": None}
    if s[-1] < g[0]:
        thr = round((s[-1] + g[0]) / 2, 3)
        out["threshold"] = thr
    else:
        cands = sorted(set(g + s))
        thr = min(cands, key=lambda t: (sum(x < t for x in g) + sum(x >= t for x in s), -t))
    out["false_reject"] = sum(x < thr for x in g)
    out["false_accept"] = sum(x >= thr for x in s)
    out["at"] = thr
    return out


def _fetch(sql, params):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description="Show logged score distribution.")
    ap.add_argument("--metric", choices=sorted(METRICS), default="face")
    ap.add_argument("--days", type=int, default=None, help="only taps in the last N days")
    ap.add_argument("--since", help="only taps from this time (HH:MM today, or date and time)")
    ap.add_argument("--until", help="only taps before this time")
    ap.add_argument("--against-since", help="start of the spoof round, to compare with")
    ap.add_argument("--against-until", help="end of the spoof round")
    args = ap.parse_args()

    score_col, verdict_col, threshold, labels = METRICS[args.metric]
    rows = _fetch(*query(score_col, verdict_col, args.days, args.since, args.until))

    if not rows:
        print(f"no {args.metric} scores yet — tap a few students first")
        return

    _report(rows, score_col, verdict_col, threshold, labels)

    if not (args.against_since or args.against_until):
        return
    other = _fetch(*query(score_col, verdict_col, args.days, args.against_since, args.against_until))
    print("\n--- against (spoof round) ---")
    if not other:
        print("no scores in that window")
        return
    _report(other, score_col, verdict_col, threshold, labels)
    sep = separation([r[0] for r in rows], [r[0] for r in other])
    print(f"\nhighest spoof = {sep['spoof_max']:.3f}, lowest genuine = {sep['genuine_min']:.3f}")
    if sep["threshold"] is not None:
        print(f"no overlap: a threshold of {sep['threshold']:.3f} separates every score here")
    else:
        print(f"the rounds overlap; fewest errors at {sep['at']:.3f}")
    print(f"at {sep['at']:.3f}: {sep['false_reject']} genuine rejected, "
          f"{sep['false_accept']} spoof accepted")


if __name__ == "__main__":
    main()
