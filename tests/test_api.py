"""
test_api.py — API-level tests for POST /zero-assistant

These tests hit the FastAPI endpoint directly (no real HTTP server needed).
All external calls (OpenAI) are mocked via conftest.py fixtures.
"""
import json
from datetime import datetime
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "cases.json").read_text()
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _case(case_id: str) -> dict:
    return next(c for c in FIXTURES if c["id"] == case_id)


def _spoken_hour_phrase(dt: datetime) -> str:
    if dt.hour == 0:
        return "凌晨12點"
    if 1 <= dt.hour <= 5:
        return f"凌晨{dt.hour}點"
    if 6 <= dt.hour <= 11:
        return f"上午{dt.hour}點"
    if dt.hour == 12:
        return "中午12點"
    if 13 <= dt.hour <= 17:
        return f"下午{dt.hour - 12}點"
    return f"晚上{dt.hour - 12}點"


# ---------------------------------------------------------------------------
# Local command tests
# ---------------------------------------------------------------------------

class TestLocalCommands:
    def test_open_photoframe(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "打開相框"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "open_photoframe"
        assert data["reply_text"]

    def test_open_album_alias(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "打開相簿"})
        assert r.status_code == 200
        assert r.json()["meta"]["action"] == "open_photoframe"

    def test_switch_album_phrase_routes_to_photoframe(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "切換相簿"})
        assert r.status_code == 200
        assert r.json()["meta"]["action"] == "open_photoframe"

    def test_simplified_open_photoframe_routes_local(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "帮我打开相框"})
        assert r.status_code == 200
        assert r.json()["meta"]["action"] == "open_photoframe"

    def test_asr_album_typo_routes_local(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "請切換相布"})
        assert r.status_code == 200
        assert r.json()["meta"]["action"] == "open_photoframe"

    def test_open_photos_alias(self, client):
        with patch("src.api.skills.open_photoframe.run", return_value="好的，已幫你打開相框。"):
            r = client.post("/zero-assistant", json={"text": "打開照片"})
        assert r.status_code == 200
        assert r.json()["meta"]["action"] == "open_photoframe"

    def test_open_bunny(self, client):
        with patch("src.api.skills.open_bunny.run", return_value="好的，已切回兔兔助理畫面。"):
            r = client.post("/zero-assistant", json={"text": "切回兔兔"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "open_bunny"

    def test_empty_input_returns_400(self, client):
        r = client.post("/zero-assistant", json={"text": ""})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Search intent detection
# ---------------------------------------------------------------------------

class TestSearchIntent:
    @pytest.mark.parametrize("text,expected_search", [
        ("高雄今天天氣如何", True),
        ("幫我查最新AI新聞", True),
        ("今天天氣怎麼樣", True),
        ("你好", False),
        ("今天幾號", False),
        ("搜尋台北美食", True),
    ])
    def test_search_tokens(self, client, text, expected_search):
        r = client.post("/zero-assistant", json={"text": text})
        assert r.status_code == 200
        data = r.json()
        # local-skill bypasses search detection, skip those
        if data["meta"].get("source") not in ("local-skill", "local-command"):
            assert data["meta"].get("search") == expected_search, (
                f"text={text!r}: expected search={expected_search}, got {data['meta'].get('search')}"
            )


# ---------------------------------------------------------------------------
# General Q&A — plain OpenAI fallback
# ---------------------------------------------------------------------------

class TestGeneralQA:
    def test_chitchat_uses_openai_fallback(self, client):
        r = client.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "fallback-openai"


class TestTimeQueries:
    def test_time_query_uses_local_skill_path(self, client):
        r = client.post("/zero-assistant", json={"text": "日本現在幾點"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "time_query"
        assert data["meta"]["timezone"] == "Asia/Tokyo"
        assert "日本現在時間是" in data["reply_text"]

    def test_date_query_uses_local_skill_path(self, client):
        r = client.post("/zero-assistant", json={"text": "今天幾號"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "time_query"
        assert data["meta"]["time_kind"] == "date"

    def test_simplified_time_query_uses_local_skill_path(self, client):
        r = client.post("/zero-assistant", json={"text": "请问现在几点"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "time_query"
        assert data["meta"]["timezone"] == "Asia/Taipei"

    def test_unknown_place_time_query_asks_for_clarification(self, client):
        r = client.post("/zero-assistant", json={"text": "巴黎現在幾點"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "time_query"
        assert data["meta"]["time_kind"] == "time"
        assert data["meta"]["timezone"] is None
        assert data["reply_text"] == "抱歉，巴黎的時區我還不確定，你可以換個地名說法嗎？"


class TestReminders:
    def test_complete_reminder_creates_local_skill_response(self, client):
        r = client.post("/zero-assistant", json={"text": "提醒我10分鐘後吃藥"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "create_reminder"
        assert data["meta"]["reminder_id"]

    def test_second_based_reminder_creates_local_skill_response(self, client):
        r = client.post("/zero-assistant", json={"text": "5秒鐘後提醒我吃藥"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "create_reminder"
        assert data["meta"]["reminder_id"]
        assert "5秒後" in data["reply_text"]

    def test_need_time_detail_starts_pending_confirmation(self, client):
        r = client.post("/zero-assistant", json={"text": "明天下午提醒我開會"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "confirm_reminder"
        assert data["meta"]["confirmation_mode"] == "need_time_detail"
        assert data["meta"]["expires_at"]

    def test_need_time_detail_follow_up_creates_reminder(self, client):
        first = client.post("/zero-assistant", json={"text": "明天下午提醒我開會"})
        assert first.status_code == 200

        second = client.post("/zero-assistant", json={"text": "三點"})
        assert second.status_code == 200
        data = second.json()
        assert data["meta"]["action"] == "create_reminder"
        assert data["meta"]["source"] == "local-skill"

    def test_confirm_candidate_decline_cancels_pending(self, client):
        late_now = datetime.now(ZoneInfo("Asia/Taipei")).replace(second=0, microsecond=0)
        if late_now.hour == 0:
            late_now = late_now.replace(hour=1, minute=0)
        past_candidate = late_now.replace(hour=late_now.hour - 1, minute=0)
        reminder_text = f"{_spoken_hour_phrase(past_candidate)}提醒我收衣服"
        with patch("src.api.skills.reminders._now_in_timezone", return_value=late_now):
            first = client.post("/zero-assistant", json={"text": reminder_text})
        assert first.status_code == 200
        assert first.json()["meta"]["confirmation_mode"] == "confirm_candidate"

        second = client.post("/zero-assistant", json={"text": "取消"})
        assert second.status_code == 200
        data = second.json()
        assert data["meta"]["action"] == "cancel_reminder"
        assert data["meta"]["source"] == "local-skill"

    def test_invalid_reminder_rejects_truthfully(self, client):
        r = client.post("/zero-assistant", json={"text": "提醒我買牛奶"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "create_reminder"
        assert data["meta"]["reminder_status"] == "rejected"
        assert data["meta"]["reason"] == "invalid_time"


# ---------------------------------------------------------------------------
# exec-plan 006 — websearch routing
# ---------------------------------------------------------------------------

class TestWebsearchRouting:
    def test_search_uses_websearch_when_enabled(self, client_with_websearch):
        """Search intent should hit run_websearch first (006 path)."""
        with patch("src.api.websearch.run_websearch", return_value="新北今天晴天，25度。") as mock_ws:
            r = client_with_websearch.post(
                "/zero-assistant", json={"text": "幫我查新北天氣"}
            )
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "openai-websearch"
        assert data["meta"]["search"] is True
        assert data["reply_text"] == "新北今天晴天，25度。"
        mock_ws.assert_called_once()

    def test_websearch_failure_falls_back_to_openai(self, client_with_websearch):
        """If websearch raises, must fall through to plain OpenAI fallback."""
        with patch("src.api.websearch.run_websearch", side_effect=RuntimeError("boom")):
            r = client_with_websearch.post(
                "/zero-assistant", json={"text": "幫我查新北天氣"}
            )
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "fallback-openai"

    def test_chitchat_does_not_use_websearch(self, client_with_websearch):
        """Non-search queries must NOT touch websearch path."""
        with patch("src.api.websearch.run_websearch") as mock_ws:
            r = client_with_websearch.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        mock_ws.assert_not_called()
        assert r.json()["meta"]["source"] == "fallback-openai"

    def test_disable_env_skips_websearch(self, client):
        """`client` fixture sets VOICEASSIST_DISABLE_WEBSEARCH=1 — must skip 006 path."""
        with patch("src.api.websearch.run_websearch") as mock_ws:
            r = client.post("/zero-assistant", json={"text": "幫我查新北天氣"})
        assert r.status_code == 200
        mock_ws.assert_not_called()
        assert r.json()["meta"]["source"] == "fallback-openai"
