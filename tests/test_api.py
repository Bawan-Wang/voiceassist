"""
test_api.py — API-level tests for POST /zero-assistant

These tests hit the FastAPI endpoint directly (no real HTTP server needed).
All external calls (openclaw, OpenAI) are mocked via conftest.py fixtures.
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
# Local command tests (no openclaw needed)
# ---------------------------------------------------------------------------

class TestLocalCommands:
    def test_open_photoframe(self, client):
        with patch("src.api.app.open_photoframe", return_value="好的，已幫你打開相框。") as mock_fn:
            r = client.post("/zero-assistant", json={"text": "打開相框"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-command"
        assert data["meta"]["action"] == "open_photoframe"
        assert data["reply_text"]

    def test_open_bunny(self, client):
        with patch("src.api.app.open_bunny_ui", return_value="好的，已切回兔兔助理畫面。") as mock_fn:
            r = client.post("/zero-assistant", json={"text": "切回兔兔"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "local-command"
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
        # local-command bypasses search detection, skip those
        if data["meta"].get("source") != "local-command":
            assert data["meta"].get("search") == expected_search, (
                f"text={text!r}: expected search={expected_search}, got {data['meta'].get('search')}"
            )


# ---------------------------------------------------------------------------
# openclaw agent routing
# ---------------------------------------------------------------------------

class TestOpenclawRouting:
    def test_general_qa_uses_openclaw(self, client):
        r = client.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "openclaw-agent"
        assert r.json()["reply_text"]

    def test_weather_uses_openclaw(self, client):
        r = client.post("/zero-assistant", json={"text": "高雄今天天氣如何"})
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "openclaw-agent"

    def test_openclaw_timeout_search_returns_hint(self, client, mock_openai):
        """When openclaw times out on a search query, return a clear message (no OpenAI fallback)."""
        import subprocess
        with patch("src.api.app.subprocess.run", side_effect=subprocess.TimeoutExpired("openclaw", 90)):
            r = client.post("/zero-assistant", json={"text": "幫我查最新消息"})
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["source"] == "openclaw-agent-timeout"
        assert "再問" in data["reply_text"] or "等" in data["reply_text"]

    def test_openclaw_failure_falls_back_to_openai(self, client, mock_openai):
        """When openclaw fails (non-search), should fall back to OpenAI."""
        with patch("src.api.app.subprocess.run", side_effect=Exception("openclaw unavailable")):
            r = client.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        # fallback-openai or still got a reply
        assert r.json()["reply_text"]

    def test_openclaw_error_json_falls_back_to_openai(self, client, mock_openai):
        """Regression for exec-plan 005: when openclaw stdout contains an error
        JSON without payloads[].text (e.g. {"error": "400 ..."}), the API must
        NOT speak the raw error string back. It should fall through to OpenAI."""
        err_proc = MagicMock()
        err_proc.stdout = json.dumps({"error": "400 input item ID does not belong to this connection"})
        err_proc.stderr = ""
        err_proc.returncode = 0
        with patch("src.api.app.subprocess.run", return_value=err_proc):
            r = client.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        data = r.json()
        # Must have fallen back to OpenAI (mocked) — NOT spoken the error string
        assert "400" not in data["reply_text"]
        assert "input item ID" not in data["reply_text"]
        assert data["meta"].get("source") == "fallback-openai"

    def test_openclaw_nonzero_returncode_falls_back(self, client, mock_openai):
        """When openclaw exits non-zero, should fall back to OpenAI even if stdout has bytes."""
        err_proc = MagicMock()
        err_proc.stdout = "{}"
        err_proc.stderr = "boom"
        err_proc.returncode = 2
        with patch("src.api.app.subprocess.run", return_value=err_proc):
            r = client.post("/zero-assistant", json={"text": "你好"})
        assert r.status_code == 200
        assert r.json()["meta"].get("source") == "fallback-openai"

    def test_openclaw_stopreason_error_falls_back(self, client, mock_openai):
        """Regression for exec-plan 005 (round 2): openclaw can return status:ok
        and returncode:0 BUT meta.stopReason:'error', wrapping the upstream error
        string into payloads[].text. Must not speak that text — fall back to OpenAI."""
        err_proc = MagicMock()
        err_proc.stdout = json.dumps({
            "runId": "x",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [{"text": "400 input item ID does not belong to this connection", "mediaUrl": None}],
                "meta": {"stopReason": "error"},
            },
        })
        err_proc.stderr = ""
        err_proc.returncode = 0
        with patch("src.api.app.subprocess.run", return_value=err_proc):
            r = client.post("/zero-assistant", json={"text": "幫我查新北天氣"})
        assert r.status_code == 200
        data = r.json()
        assert "400" not in data["reply_text"]
        assert "input item ID" not in data["reply_text"]
        assert data["meta"].get("source") == "fallback-openai"
