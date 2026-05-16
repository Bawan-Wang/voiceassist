"""
test_api.py — API-level tests for POST /zero-assistant

These tests hit the FastAPI endpoint directly (no real HTTP server needed).
All external calls (OpenAI) are mocked via conftest.py fixtures.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "cases.json").read_text()
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _case(case_id: str) -> dict:
    return next(c for c in FIXTURES if c["id"] == case_id)


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

    def test_unknown_place_time_query_asks_for_clarification(self, client):
        r = client.post("/zero-assistant", json={"text": "巴黎現在幾點"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-skill"
        assert data["meta"]["action"] == "time_query"
        assert data["meta"]["time_kind"] == "time"
        assert data["meta"]["timezone"] is None
        assert data["reply_text"] == "抱歉，巴黎的時區我還不確定，你可以換個地名說法嗎？"


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
