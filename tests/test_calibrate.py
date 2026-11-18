"""The calibration helper's windows and threshold suggestion (PC-025). No database."""

from datetime import date

import pytest

from backend import calibrate


def test_summarize_reports_the_same_numbers_the_cli_prints():
    rows = [(0.9, True), (0.95, True), (0.05, False)]
    s = calibrate.summarize(rows, threshold=0.5, labels=("live", "spoof"))
    assert s["count"] == 3 and s["pos"] == 2 and s["neg"] == 1
    assert s["min"] == pytest.approx(0.05) and s["max"] == pytest.approx(0.95)
    assert s["threshold"] == 0.5
    assert sum(b["count"] for b in s["histogram"]) == 3


def test_the_api_route_serves_the_same_summary(client, monkeypatch):
    from backend import calibrate as c

    rows = [(0.9, True), (0.95, True), (0.05, False)]
    monkeypatch.setattr(c, "_fetch", lambda *a, **k: rows)

    r = client.get("/api/calibrate?metric=liveness")
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "liveness"
    assert body["count"] == 3 and body["pos"] == 2 and body["neg"] == 1


def test_the_api_route_handles_no_scores_yet(client, monkeypatch):
    from backend import calibrate as c

    monkeypatch.setattr(c, "_fetch", lambda *a, **k: [])
    r = client.get("/api/calibrate?metric=face")
    assert r.status_code == 200
    assert r.json() == {"metric": "face", "count": 0, "threshold": 0.5}


def test_an_unknown_metric_is_rejected(client):
    r = client.get("/api/calibrate?metric=nonsense")
    assert r.status_code == 422

DAY = date(2026, 11, 18)


def test_hh_mm_means_today_and_anything_else_is_kept():
    assert calibrate.when("09:05", DAY) == "2026-11-18 09:05"
    assert calibrate.when("2026-11-18 09:05", DAY) == "2026-11-18 09:05"
    assert calibrate.when(None) is None


def test_the_window_goes_into_the_query_as_parameters():
    sql, params = calibrate.query("liveness_score", "liveness_pass", since="09:00",
                                  until="09:20", today=DAY)
    assert "ts >= %s::timestamptz" in sql and "ts < %s::timestamptz" in sql
    assert params == ["2026-11-18 09:00", "2026-11-18 09:20"]


def test_no_overlap_gives_the_midpoint_and_no_errors():
    sep = calibrate.separation([0.81, 0.86, 0.9], [0.05, 0.2, 0.41])
    assert sep["threshold"] == 0.61
    assert sep["false_reject"] == 0 and sep["false_accept"] == 0


def test_overlap_gives_the_point_with_fewest_errors():
    sep = calibrate.separation([0.3, 0.8, 0.9], [0.1, 0.5])
    assert sep["threshold"] is None
    assert sep["false_reject"] + sep["false_accept"] == 1
