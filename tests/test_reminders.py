import json
from src.api.skills.reminders import parse_reminder, create_reminder_from_result


def test_parse_relative_minute():
    res = parse_reminder("提醒我10分鐘後吃藥")
    assert res is not None
    assert res.mode == "create"
    assert res.task == "吃藥" or "提醒事項"
    assert res.when_iso is not None


def test_parse_absolute_time():
    res = parse_reminder("提醒我在14點吃藥")
    assert res is not None
    assert res.mode == "create"
    assert res.task is not None
    assert res.when_iso is not None


def test_parse_confirm_candidate():
    res = parse_reminder("提醒我買牛奶")
    assert res is not None
    assert res.mode == "confirm_candidate"


def test_app_create_reminder(client):
    # client fixture from tests/conftest posts to /zero-assistant
    resp = client.post("/zero-assistant", json={"text": "提醒我10分鐘後吃藥"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("meta", {}).get("action") == "reminder_create"
    assert "id" in data.get("meta", {})
