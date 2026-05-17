from datetime import datetime, timedelta

from src.api.skills import reminder_store
from src.api.skills import reminders as reminder_logic


def test_add_list_and_mark_delivered(tmp_path):
    # isolate paths
    reminders_path = tmp_path / "reminders.json"
    pending_path = tmp_path / "reminder_pending.json"

    reminder_store.REMINDERS_PATH = reminders_path
    reminder_store.PENDING_PATH = pending_path

    # clean start
    assert reminder_store.list_reminders() == []

    entry = reminder_store.add_reminder("測試任務", (datetime.now() + timedelta(seconds=1)).astimezone().isoformat())
    assert isinstance(entry, dict)
    rs = reminder_store.list_reminders()
    assert len(rs) == 1
    assert rs[0]["task_text"] == "測試任務"
    assert rs[0]["status"] == "pending"

    # mark delivered
    reminder_store.mark_delivered(entry["id"])
    rs2 = reminder_store.list_reminders()
    assert rs2[0]["status"] == "delivered"
    assert rs2[0]["delivered_at"] is not None


def test_pending_start_and_clear(tmp_path):
    reminders_path = tmp_path / "reminders.json"
    pending_path = tmp_path / "reminder_pending.json"

    reminder_store.REMINDERS_PATH = reminders_path
    reminder_store.PENDING_PATH = pending_path

    result = reminder_logic.parse_reminder(
        "明天下午提醒我買牛奶",
        now=datetime.fromisoformat("2026-05-17T09:00:00+08:00"),
    )
    assert result is not None
    assert result.mode == "need_time_detail"

    p = reminder_logic.start_pending_confirmation(result, original_text="明天下午提醒我買牛奶", ttl_sec=2)
    assert p is not None
    read = reminder_store.read_pending()
    assert read is not None
    assert read.get("mode") == "need_time_detail"
    assert read.get("task_text") == "買牛奶"

    # clear pending
    reminder_store.clear_pending()
    assert reminder_store.read_pending() is None
