"""The attendance clock: which time zone the database session counts days in.

Postgres in Docker runs on UTC. Left alone, `ts::date` files a 07:30 tap in a UTC+8
school under the previous day and compares 23:30 against LATE_CUTOFF. `backend.db`
therefore switches every session to the school's zone. No database is used here; the
connection is a recording fake.
"""

import os
from datetime import timedelta

import pytest

from backend import db


class RecordingConnection:
    def __init__(self, fail=None):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self._fail = fail

    def cursor(self, *args, **kwargs):
        conn = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                if conn._fail is not None:
                    raise conn._fail
                conn.executed.append((sql, params))

        return Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("/usr/share/zoneinfo/Asia/Manila", "Asia/Manila"),
        ("/var/db/timezone/zoneinfo/America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires"),
        ("/usr/share/zoneinfo/Etc/UTC", "Etc/UTC"),
    ],
)
def test_system_zone_is_read_from_the_localtime_link(monkeypatch, link, expected):
    monkeypatch.setattr(os.path, "realpath", lambda path: link)

    assert db._system_timezone() == expected


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(hours=8), "<+0800>-08:00"),
        (timedelta(hours=-5), "<-0500>+05:00"),
        (timedelta(hours=5, minutes=30), "<+0530>-05:30"),
        (timedelta(0), "<+0000>-00:00"),
    ],
)
def test_system_zone_falls_back_to_the_utc_offset(monkeypatch, offset, expected):
    # /etc/localtime is a plain file on some systems, so there is no name to read.
    monkeypatch.setattr(os.path, "realpath", lambda path: "/etc/localtime")
    monkeypatch.setattr(db, "_local_utc_offset", lambda: offset)

    assert db._system_timezone() == expected


def test_system_zone_is_unknown_when_the_offset_is(monkeypatch):
    monkeypatch.setattr(os.path, "realpath", lambda path: "/etc/localtime")
    monkeypatch.setattr(db, "_local_utc_offset", lambda: None)

    assert db._system_timezone() is None


def test_this_machine_reports_a_usable_offset():
    offset = db._local_utc_offset()

    assert offset is not None and abs(offset) <= timedelta(hours=14)


def test_session_is_switched_to_the_attendance_zone(monkeypatch):
    monkeypatch.setattr(db, "SESSION_TZ", "Asia/Manila")
    conn = RecordingConnection()

    db._use_attendance_clock(conn)

    assert conn.executed == [("SET TIME ZONE %s", ("Asia/Manila",))]
    assert conn.commits == 1, "an uncommitted SET would be undone by a later rollback"


def test_no_zone_means_the_session_is_left_alone(monkeypatch):
    monkeypatch.setattr(db, "SESSION_TZ", None)
    conn = RecordingConnection()

    db._use_attendance_clock(conn)

    assert conn.executed == [] and conn.commits == 0


def test_an_unknown_zone_is_reported_once_and_does_not_break_the_connection(monkeypatch, capsys):
    monkeypatch.setattr(db, "SESSION_TZ", "Mars/Olympus_Mons")
    monkeypatch.setattr(db, "_tz_warned", False)

    for _ in range(3):
        conn = RecordingConnection(fail=RuntimeError('invalid value for parameter "TimeZone"'))
        db._use_attendance_clock(conn)  # must not raise
        assert conn.rollbacks == 1, "the failed SET has to be cleared before the session is used"

    printed = capsys.readouterr().out
    assert printed.count("could not set session time zone") == 1
    assert "Mars/Olympus_Mons" in printed


def test_every_connection_goes_through_the_attendance_clock(monkeypatch):
    conn = RecordingConnection()
    monkeypatch.setattr(db.psycopg2, "connect", lambda dsn: conn)
    monkeypatch.setattr(db, "register_vector", lambda c: None)
    monkeypatch.setattr(db, "SESSION_TZ", "Asia/Manila")

    with db.get_conn() as got:
        assert got is conn
        assert conn.executed == [("SET TIME ZONE %s", ("Asia/Manila",))]

    assert conn.closed
