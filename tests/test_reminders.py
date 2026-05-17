from datetime import datetime

from src.api.skills.reminders import parse_reminder


FIXED_NOW = datetime.fromisoformat("2026-05-17T09:00:00+08:00")


def test_parse_relative_minute():
    res = parse_reminder("提醒我10分鐘後吃藥", now=FIXED_NOW)
    assert res is not None
    assert res.mode == "create"
    assert res.task_text == "吃藥"
    assert res.due_at is not None
    assert res.timezone == "Asia/Taipei"


def test_parse_absolute_time():
    res = parse_reminder("提醒我今天18點吃藥", now=FIXED_NOW)
    assert res is not None
    assert res.mode == "create"
    assert res.task_text == "吃藥"
    assert res.due_at is not None


def test_parse_confirm_candidate():
    late_now = datetime.fromisoformat("2026-05-17T22:00:00+08:00")
    res = parse_reminder("晚上九點提醒我收衣服", now=late_now)
    assert res is not None
    assert res.mode == "confirm_candidate"
    assert res.candidate_due_at is not None


def test_parse_missing_time_rejects():
    res = parse_reminder("提醒我買牛奶", now=FIXED_NOW)
    assert res is not None
    assert res.mode == "reject"
    assert res.reason == "invalid_time"


def test_parse_need_time_detail():
    res = parse_reminder("明天下午提醒我開會", now=FIXED_NOW)
    assert res is not None
    assert res.mode == "need_time_detail"
    assert res.task_text == "開會"
    assert res.pending is not None
    assert res.pending.get("time_hint_prefix") == "明天下午"


def test_app_create_reminder(client):
    # client fixture from tests/conftest posts to /zero-assistant
    resp = client.post("/zero-assistant", json={"text": "提醒我10分鐘後吃藥"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("meta", {}).get("action") == "create_reminder"
    assert "reminder_id" in data.get("meta", {})
