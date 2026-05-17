import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.api.skills import reminder_store
from src.api.skills.reminders import parse_reminder, start_pending_confirmation
from src.api.skills.policy import RouteKind
from src.bridge import voice_bridge


def _make_bridge(tmp_path, spoken):
    bridge = object.__new__(voice_bridge.VoiceBridge)
    bridge.cfg = SimpleNamespace(state_path=tmp_path / "voice-state.json")
    bridge._bridge_phase = "idle"
    bridge._is_speaking = False
    bridge.speak = lambda text: spoken.append(text)
    return bridge


def test_voice_bridge_classifies_reminder_route():
    decision = voice_bridge.classify_request("明天早上八點提醒我買咖啡")

    assert decision.kind == RouteKind.REMINDER


def test_pending_follow_up_bypasses_normal_routing(tmp_path):
    spoken = []
    bridge = _make_bridge(tmp_path, spoken)
    api_prompts = []
    bridge._reply_via_api = lambda prompt: api_prompts.append(prompt) or "好，我會在明天下午三點提醒你開會。"

    pending = parse_reminder("明天下午提醒我開會", now=datetime.fromisoformat("2026-05-17T09:00:00+08:00"))
    assert pending is not None
    assert pending.mode == "need_time_detail"
    start_pending_confirmation(pending, original_text="明天下午提醒我開會")

    assert bridge._process_pending_follow_up("三點") is True
    assert api_prompts == ["三點"]
    assert spoken == ["好，我會在明天下午三點提醒你開會。"]


def test_due_delivery_waits_until_idle(tmp_path):
    spoken = []
    bridge = _make_bridge(tmp_path, spoken)
    bridge._bridge_phase = "thinking"

    reminder_store.add_reminder("任務A", (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    bridge._deliver_due_reminders_once()

    assert spoken == []
    reminders = reminder_store.list_reminders()
    assert reminders[0]["status"] == "pending"


def test_due_delivery_drains_oldest_first(tmp_path):
    spoken = []
    bridge = _make_bridge(tmp_path, spoken)

    older = datetime.now(timezone.utc) - timedelta(minutes=2)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    reminder_store.add_reminder("任務A", newer.isoformat())
    reminder_store.add_reminder("任務B", older.isoformat())

    bridge._deliver_due_reminders_once()

    assert spoken == ["提醒你，任務B。", "提醒你，任務A。"]
    reminders = reminder_store.list_reminders()
    assert [reminder["status"] for reminder in reminders] == ["delivered", "delivered"]

    state = json.loads((tmp_path / "voice-state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "idle"
    assert state["assistantText"] == "提醒你，任務A。"