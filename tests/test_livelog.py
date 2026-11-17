"""The dashboard's live log and scan steps (backend/livelog.py)."""

import io

import pytest

from backend import livelog


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(livelog, "_buf", livelog.collections.deque(maxlen=livelog.MAX_LINES))
    published = []
    monkeypatch.setattr(livelog.events, "publish", published.append)
    return published


@pytest.mark.parametrize("text, hidden", [
    ("send failed: 550 guardian@example.com rejected", "guardian@example.com"),
    ("sms to 09171234567 failed", "09171234567"),
    ("sms to +639171234567 failed", "+639171234567"),
])
def test_contacts_never_reach_the_screen(text, hidden):
    livelog.record(text)
    line = livelog.recent()[-1]["text"]
    assert hidden not in line and "<" in line


def test_a_secret_setting_is_masked(monkeypatch):
    monkeypatch.setenv("SEMAPHORE_API_KEY", "abcdef0123456789")
    livelog.record("POST ...?apikey=abcdef0123456789")
    assert "abcdef0123456789" not in livelog.recent()[-1]["text"]


def test_card_uids_and_scores_stay():
    livelog.record("[matcher] tap uid=3163E4B0: window closed, face 0.70")
    assert "3163E4B0" in livelog.recent()[-1]["text"]


def test_the_tee_records_whole_lines_and_writes_through(fresh):
    out = io.StringIO()
    tee = livelog._Tee(out, "out")
    tee.write("[perception] track 1")
    tee.write(": recognized\nsecond line\n")
    assert out.getvalue() == "[perception] track 1: recognized\nsecond line\n"
    assert [l["text"] for l in livelog.recent()] == ["[perception] track 1: recognized", "second line"]
    assert [e["type"] for e in fresh] == ["log", "log"]


def test_a_closed_stream_does_not_break_a_print():
    out = io.StringIO()
    tee = livelog._Tee(out, "out")
    out.close()
    tee.write("still recorded\n")
    assert livelog.recent()[-1]["text"] == "still recorded"


def test_the_buffer_keeps_the_latest_lines():
    for n in range(livelog.MAX_LINES + 10):
        livelog.record(f"line {n}")
    lines = livelog.recent(livelog.MAX_LINES)
    assert len(lines) == livelog.MAX_LINES and lines[-1]["text"] == f"line {livelog.MAX_LINES + 9}"
    assert len(livelog.recent(5)) == 5


def test_a_stage_is_published_and_printed(fresh, capsys):
    livelog.stage("3163E4B0", "verdict", "accepted", done=True)
    ev = [e for e in fresh if e["type"] == "stage"][0]
    assert ev["uid"] == "3163E4B0" and ev["stage"] == "verdict" and ev["done"] is True
    assert "[scan] 3163E4B0 verdict: accepted" in capsys.readouterr().out


def test_a_tap_walks_through_its_steps(client, fake_db, sinks):
    fake_db.add_student({"student_id": "S001", "uid": "C3BE343A", "name": "Test Student",
                         "face_embedding": [0.1, 0.2, 0.3], "face_consent": False})
    client.post("/tap", json={"uid": "C3BE343A"})
    steps = [e["stage"] for e in sinks.stages]
    assert steps[:2] == ["card", "student"] and steps[-2:] == ["verdict", "notify"]
    assert sinks.stages[-1]["done"] is True


def test_an_unknown_card_ends_at_not_on_the_roster(client, sinks, monkeypatch):
    from backend import perception

    monkeypatch.setattr(perception, "PERCEPTION_ENABLED", True)
    client.post("/tap", json={"uid": "DEADBEEF"})
    assert [e["text"] for e in sinks.stages][:2] == ["card read", "not on the roster"]
    assert sinks.stages[-1]["text"] == "no guardian message"


def test_the_logs_endpoint_returns_recent_lines(client):
    livelog.record("hello from the backend")
    lines = client.get("/api/logs?limit=5").json()["lines"]
    assert lines[-1]["text"] == "hello from the backend"
