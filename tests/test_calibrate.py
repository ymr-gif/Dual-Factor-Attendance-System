"""The calibration helper's windows and threshold suggestion (PC-025). No database."""

from datetime import date

from backend import calibrate

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
