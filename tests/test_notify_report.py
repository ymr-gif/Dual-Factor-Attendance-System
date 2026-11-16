"""The delivery and latency report (PC-020): pure arithmetic over notification_log
rows, plus the two endpoints that serve it.
"""

import csv
import io
from datetime import datetime, time, timedelta, timezone

import pytest

from backend import notify_report

MANILA = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def peak_window(monkeypatch):
    monkeypatch.setattr(notify_report, "PEAK_START", time(7, 0))
    monkeypatch.setattr(notify_report, "PEAK_END", time(7, 30))


def at(hour, minute, second=0):
    """A school-clock time on Nov 24, 2026, as the database hands it over (UTC)."""
    return datetime(2026, 11, 24, hour, minute, second, tzinfo=MANILA).astimezone(timezone.utc)


def row(status="DELIVERED", latency_ms=None, t0=None, channel="email", **over):
    t0 = t0 or at(7, 10)
    r = {
        "id": 1,
        "log_id": 1,
        "channel": channel,
        "t0": t0,
        "t1": t0 + timedelta(milliseconds=latency_ms) if latency_ms is not None else None,
        "latency_ms": latency_ms,
        "status": status,
        "provider_message_id": None,
        "error": None,
        "attempts": 1,
    }
    r.update(over)
    return r


# --- peak ---


@pytest.mark.parametrize(
    "t0, expected",
    [
        (at(6, 59, 59), False),
        (at(7, 0), True),
        (at(7, 29, 59), True),
        (at(7, 30), False),  # the end of the window is not in it
        (at(12, 0), False),
    ],
)
def test_peak_is_the_arrival_window_on_the_school_clock(t0, expected):
    assert notify_report.is_peak(t0, MANILA) is expected


def test_peak_is_not_read_off_the_utc_clock():
    seven_utc = datetime(2026, 11, 24, 7, 10, tzinfo=timezone.utc)  # 3:10 PM in Manila
    assert notify_report.is_peak(seven_utc, MANILA) is False


@pytest.mark.parametrize("bad", [None, "", "7", "seven:ten", "25:00", "07:61"])
def test_a_bad_peak_setting_falls_back_to_the_default(bad):
    assert notify_report._clock(bad, time(7, 0)) == time(7, 0)


def test_a_peak_setting_is_read_as_hh_mm():
    assert notify_report._clock("06:45", time(7, 0)) == time(6, 45)


# --- delivery rate ---


def test_delivery_rate_is_delivered_over_delivered_plus_failed():
    rows = [row(latency_ms=1000)] * 3 + [row("FAILED")]

    block = notify_report.summarize(rows, MANILA)["channels"]["email"]["all"]

    assert block["counts"] == {"DELIVERED": 3, "FAILED": 1, "DISABLED": 0, "PENDING": 0}
    assert block["delivery_rate"] == 0.75


def test_disabled_and_pending_rows_are_left_out_of_the_rate():
    rows = [row(latency_ms=1000), row("DISABLED"), row("DISABLED"), row("PENDING")]

    block = notify_report.summarize(rows, MANILA)["channels"]["email"]["all"]

    assert block["counts"]["DISABLED"] == 2
    assert block["counts"]["PENDING"] == 1
    assert block["delivery_rate"] == 1.0


def test_no_attempt_means_no_rate_not_zero():
    block = notify_report.summarize([row("DISABLED")], MANILA)["channels"]["email"]["all"]

    assert block["delivery_rate"] is None
    assert block["latency_s"]["n"] == 0
    assert block["latency_s"]["mean"] is None


# --- latency ---


def test_latency_is_in_seconds_over_delivered_rows_only():
    rows = [row(latency_ms=1000), row(latency_ms=2000), row(latency_ms=6000), row("FAILED")]

    lat = notify_report.summarize(rows, MANILA)["channels"]["email"]["all"]["latency_s"]

    assert lat == {"n": 3, "mean": 3.0, "sd": 2.646, "median": 2.0, "min": 1.0, "max": 6.0}


def test_the_sd_is_the_sample_sd_and_needs_two_rows():
    one = notify_report.summarize([row(latency_ms=1500)], MANILA)
    two = notify_report.summarize([row(latency_ms=1000), row(latency_ms=3000)], MANILA)

    assert one["channels"]["email"]["all"]["latency_s"]["sd"] is None
    assert two["channels"]["email"]["all"]["latency_s"]["sd"] == 1.414  # n - 1


# --- the split ---


def test_peak_and_off_peak_are_reported_apart():
    rows = [
        row(latency_ms=4000, t0=at(7, 5)),
        row(latency_ms=6000, t0=at(7, 20)),
        row("FAILED", t0=at(7, 25)),
        row(latency_ms=1000, t0=at(9, 0)),
    ]

    email = notify_report.summarize(rows, MANILA)["channels"]["email"]

    assert email["peak"]["latency_s"]["mean"] == 5.0
    assert email["peak"]["delivery_rate"] == 0.6667
    assert email["off_peak"]["latency_s"]["mean"] == 1.0
    assert email["off_peak"]["delivery_rate"] == 1.0
    assert email["all"]["latency_s"]["n"] == 3


def test_each_channel_has_its_own_block():
    rows = [row(latency_ms=1000), row("DISABLED", channel="sms")]

    report = notify_report.summarize(rows, MANILA)

    assert sorted(report["channels"]) == ["email", "sms"]
    assert report["channels"]["sms"]["all"]["counts"]["DISABLED"] == 1
    assert report["rows"] == 2
    assert report["peak_window"] == "07:00 to 07:30"


def test_an_empty_log_gives_an_empty_report():
    assert notify_report.summarize([], MANILA) == {
        "peak_window": "07:00 to 07:30", "rows": 0, "channels": {}}


# --- the endpoints ---


@pytest.fixture
def logged(fake_db, monkeypatch):
    from backend import notify

    monkeypatch.setattr(notify, "SCHOOL_ZONE", MANILA)
    fake_db.notifications = [
        dict(row(latency_ms=2000, t0=at(7, 10)), id=1, log_id=11),
        dict(row("FAILED", t0=at(9, 0), error="SMTPServerDisconnected"), id=2, log_id=12),
        dict(row("DISABLED", channel="sms", error="NOTIFY_SMS_ENABLED is off"), id=3,
             log_id=11),
    ]
    return fake_db


def test_the_summary_endpoint_serves_the_report(client, logged):
    r = client.get("/api/notifications/summary")

    assert r.status_code == 200
    email = r.json()["channels"]["email"]
    assert email["all"]["delivery_rate"] == 0.5
    assert email["peak"]["latency_s"]["mean"] == 2.0
    assert email["off_peak"]["counts"]["FAILED"] == 1


def test_the_csv_export_has_one_line_per_row_and_the_peak_flag(client, logged):
    r = client.get("/api/notifications.csv")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = list(csv.reader(io.StringIO(r.text)))
    assert tuple(lines[0]) == notify_report.CSV_COLUMNS
    assert len(lines) == 4
    by_id = {line[0]: dict(zip(lines[0], line)) for line in lines[1:]}
    assert by_id["1"]["status"] == "DELIVERED" and by_id["1"]["latency_ms"] == "2000"
    assert by_id["1"]["peak"] == "True"
    assert by_id["2"]["peak"] == "False"
    assert by_id["2"]["error"] == "SMTPServerDisconnected"


def test_the_export_has_no_column_for_a_student_or_a_contact():
    for column in notify_report.CSV_COLUMNS:
        assert column not in ("student_id", "uid", "name", "recipient", "to",
                              "guardian_email", "guardian_mobile")


def test_the_report_endpoints_need_the_operator_token(client, backend_main, monkeypatch):
    monkeypatch.setattr(backend_main, "OPERATOR_TOKEN", "s3cret-operator-token")

    assert client.get("/api/notifications/summary").status_code == 401
    assert client.get("/api/notifications.csv").status_code == 401
