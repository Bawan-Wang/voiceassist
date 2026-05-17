from datetime import datetime, timedelta

from src.api.skills import reminder_store


def test_delivery_simulation_marks_delivered(tmp_path):
    reminders_path = tmp_path / "reminders.json"
    reminder_store.REMINDERS_PATH = reminders_path
    reminder_store.LEGACY_REMINDERS_PATH = tmp_path / "legacy-reminders.json"

    entry = reminder_store.add_reminder(
        "任務A",
        (datetime.now().astimezone() - timedelta(seconds=10)).isoformat(),
    )

    # simulate one iteration of poller
    rs = reminder_store.list_reminders()
    assert len(rs) == 1
    assert rs[0]["status"] == "pending"

    # fake speak
    spoken = []

    def fake_speak(text: str):
        spoken.append(text)

    # emulate poller behavior
    now = datetime.now().astimezone()
    due_items = [r for r in rs if r.get("status") == "pending" and r.get("due_at")]
    due_sorted = sorted(due_items, key=lambda r: r.get("due_at"))
    for r in due_sorted:
        try:
            due_dt = datetime.fromisoformat(r.get("due_at"))
        except Exception:
            continue
        if due_dt <= now:
            fake_speak(f"提醒你，{r.get('task_text')}")
            reminder_store.mark_delivered(r.get("id"))

    assert len(spoken) == 1
    updated = reminder_store.list_reminders()
    assert updated[0]["id"] == entry["id"]
    assert updated[0]["status"] == "delivered"
