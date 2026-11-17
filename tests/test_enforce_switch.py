"""The two-factor switch on the Settings page (enforce_2fa).

Off by default. A value saved on the Settings page wins over ENFORCE_2FA, takes effect
on the next tap without a restart, and every change is audited.
"""

from backend import db, decision

STUDENT = {"student_id": "S001", "name": "Ana"}


def test_off_by_default(monkeypatch):
    monkeypatch.setattr(decision, "ENFORCE_2FA", False)
    assert decision.enforcing() is False
    assert decision.decide(STUDENT, False, True) == decision.FLAGGED


def test_a_saved_value_wins_over_the_env_default(monkeypatch, settings_store):
    monkeypatch.setattr(decision, "ENFORCE_2FA", False)
    settings_store["enforce_2fa"] = "true"
    assert decision.decide(STUDENT, False, True) == decision.REJECTED
    monkeypatch.setattr(decision, "ENFORCE_2FA", True)
    settings_store["enforce_2fa"] = "false"
    assert decision.decide(STUDENT, False, True) == decision.FLAGGED


def test_an_unreadable_settings_table_falls_back_to_the_env_default(monkeypatch):
    def broken(key, default=None):
        raise RuntimeError("database down")

    monkeypatch.setattr(db, "get_setting", broken)
    monkeypatch.setattr(decision, "ENFORCE_2FA", True)
    assert decision.decide(STUDENT, False, True) == decision.REJECTED


def test_the_switch_changes_the_next_tap_and_is_audited(client, fake_db, camera):
    camera.sees(score=0.1, live_score=0.97, is_live=True)  # face below the 0.5 threshold
    fake_db.add_student({"student_id": "S001", "uid": "04AA", "name": "Ana",
                         "face_embedding": [0.1, 0.2, 0.3], "face_consent": False})
    r = client.post("/tap", json={"uid": "04AA"})
    assert r.json()["log"]["status"] == "flagged"

    r = client.put("/api/settings", json={"key": "enforce_2fa", "value": "true"},
                   headers={"X-Operator-Actor": "guard1"})
    assert r.status_code == 200
    assert client.get("/api/config").json()["decision"]["enforce_2fa"] is True
    assert ("guard1", "setting", "enforce_2fa", "true") in [
        (a["actor"], a["action"], a["target"], a["detail"]) for a in fake_db.audits
    ]

    r = client.post("/tap", json={"uid": "04AA"})
    assert r.json()["log"]["status"] == "rejected"


def test_a_switch_takes_only_true_or_false(client, settings_store):
    r = client.put("/api/settings", json={"key": "enforce_2fa", "value": "yes please"})
    assert r.status_code == 422
    assert "enforce_2fa" not in settings_store
