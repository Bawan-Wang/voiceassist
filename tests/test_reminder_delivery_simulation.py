from datetime import datetime, timedelta
import json
from pathlib import Path

from src.api.skills import reminder_store


def test_delivery_simulation_marks_delivered(tmp_path):
    reminders_path = tmp_path / "reminders.json"
    reminder_store.REMINDERS_PATH = reminders_path

    due = (datetime.now().astimezone() - timedelta(seconds=10)).isoformat()
    reminders = [
        {"id": "r1", "task": "任務A", "due": due, "created": datetime.now().astimezone().isoformat(), "delivered": False},
    ]
    reminders_path.write_text(json.dumps(reminders, ensure_ascii=False))

    # simulate one iteration of poller
    rs = reminder_store.list_reminders()
    assert len(rs) == 1
    assert not rs[0]["delivered"]

    # fake speak
    spoken = []
    def fake_speak(text: str):
        spoken.append(text)

    # emulate poller behavior
    now = datetime.now().astimezone()
    due_items = [r for r in rs if not r.get('delivered') and r.get('due')]
    due_sorted = sorted(due_items, key=lambda r: r.get('due'))
    for r in due_sorted:
        try:
            due_dt = datetime.fromisoformat(r.get('due'))
        except Exception:
            continue
        if due_dt <= now:
            fake_speak(f"提醒：{r.get('task')}")
            reminder_store.mark_delivered(r.get('id'))

    assert len(spoken) == 1
    updated = reminder_store.list_reminders()
    assert updated[0]['delivered'] is True
