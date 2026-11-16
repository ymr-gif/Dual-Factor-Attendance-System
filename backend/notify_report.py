"""Delivery rate and latency of guardian notifications (PC-020).

Works on `notification_log` rows as `db.get_notifications()` returns them and touches
nothing else, so the numbers in the study can be recomputed from the exported CSV.

Per channel, for all entries and split into peak and off-peak:
  counts         rows by status
  delivery_rate  DELIVERED / (DELIVERED + FAILED). DISABLED rows (channel off, or no
                 recipient) and PENDING rows (not finished) are left out.
  latency_s      n, mean, sd (sample, n - 1), median, min and max of t1 - t0 in
                 seconds, over DELIVERED rows.

Env:
  PEAK_START / PEAK_END  the peak arrival window on the school clock, HH:MM
                         (default 07:00 to 07:30; the end is not included)
"""

import os
import statistics
from datetime import time

STATUSES = ("DELIVERED", "FAILED", "DISABLED", "PENDING")
CSV_COLUMNS = ("id", "log_id", "channel", "t0", "t1", "latency_ms", "status",
               "provider_message_id", "error", "attempts", "peak")


def _clock(value: str | None, default: time) -> time:
    try:
        hour, minute = (value or "").strip().split(":")
        return time(int(hour), int(minute))
    except ValueError:
        if value:
            print(f"[notify_report] {value!r} is not HH:MM; using {default:%H:%M}")
        return default


PEAK_START = _clock(os.environ.get("PEAK_START"), time(7, 0))
PEAK_END = _clock(os.environ.get("PEAK_END"), time(7, 30))


def is_peak(t0, zone=None) -> bool:
    """Whether an entry fell in the peak arrival window, on the school clock."""
    if t0.tzinfo is not None:
        t0 = t0.astimezone(zone)
    return PEAK_START <= t0.time() < PEAK_END


def _latency(rows) -> dict:
    seconds = [r["latency_ms"] / 1000 for r in rows
               if r["status"] == "DELIVERED" and r.get("latency_ms") is not None]
    if not seconds:
        return {"n": 0, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    return {
        "n": len(seconds),
        "mean": round(statistics.fmean(seconds), 3),
        "sd": round(statistics.stdev(seconds), 3) if len(seconds) > 1 else None,
        "median": round(statistics.median(seconds), 3),
        "min": round(min(seconds), 3),
        "max": round(max(seconds), 3),
    }


def _block(rows) -> dict:
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    tried = counts["DELIVERED"] + counts["FAILED"]
    return {
        "counts": counts,
        "delivery_rate": round(counts["DELIVERED"] / tried, 4) if tried else None,
        "latency_s": _latency(rows),
    }


def summarize(rows, zone=None) -> dict:
    """The report: one block per channel, each for all rows, peak and off-peak."""
    channels = {}
    for channel in sorted({r["channel"] for r in rows}):
        mine = [r for r in rows if r["channel"] == channel]
        peak = [r for r in mine if is_peak(r["t0"], zone)]
        off_peak = [r for r in mine if not is_peak(r["t0"], zone)]
        channels[channel] = {
            "all": _block(mine),
            "peak": _block(peak),
            "off_peak": _block(off_peak),
        }
    return {
        "peak_window": f"{PEAK_START:%H:%M} to {PEAK_END:%H:%M}",
        "rows": len(rows),
        "channels": channels,
    }


def csv_rows(rows, zone=None):
    """The rows as lists in CSV_COLUMNS order, with the peak flag worked out."""
    for r in rows:
        row = dict(r, peak=is_peak(r["t0"], zone))
        yield [row.get(c) for c in CSV_COLUMNS]
