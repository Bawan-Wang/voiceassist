"""
test_websearch_provider.py — unit tests for src/api/websearch.run_websearch
"""
import os
import pytest
from unittest.mock import patch, MagicMock


def _mk_resp(text: str) -> MagicMock:
    content = MagicMock()
    content.type = "output_text"
    content.text = text
    item = MagicMock()
    item.content = [content]
    resp = MagicMock()
    resp.output = [item]
    resp.output_text = text
    return resp


class TestRunWebsearch:
    def test_returns_clean_text(self):
        from src.api import websearch

        with patch("openai.OpenAI") as mock_cls:
            instance = MagicMock()
            instance.responses.create.return_value = _mk_resp("新北今天晴時多雲，氣溫25度。")
            mock_cls.return_value = instance

            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
                out = websearch.run_websearch("幫我查新北天氣")

        assert "新北" in out
        # tools must include web_search
        call_kwargs = instance.responses.create.call_args.kwargs
        assert any(t.get("type") == "web_search" for t in call_kwargs["tools"])

    def test_disabled_via_env_raises(self):
        from src.api import websearch

        with patch.dict(os.environ, {"VOICEASSIST_DISABLE_WEBSEARCH": "1"}, clear=False):
            with pytest.raises(RuntimeError, match="disabled"):
                websearch.run_websearch("查天氣")

    def test_empty_query_raises(self):
        from src.api import websearch

        with patch.dict(os.environ, {"VOICEASSIST_DISABLE_WEBSEARCH": "0"}, clear=False):
            with pytest.raises(ValueError):
                websearch.run_websearch("   ")

    def test_missing_api_key_raises(self):
        from src.api import websearch

        with patch.dict(os.environ, {"VOICEASSIST_DISABLE_WEBSEARCH": "0", "OPENAI_API_KEY": ""}, clear=False):
            with patch("src.api.websearch._resolve_api_key", return_value=""):
                with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                    websearch.run_websearch("查天氣")

    def test_empty_response_raises(self):
        from src.api import websearch

        with patch("openai.OpenAI") as mock_cls:
            instance = MagicMock()
            instance.responses.create.return_value = _mk_resp("")
            mock_cls.return_value = instance

            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
                with pytest.raises(RuntimeError, match="empty"):
                    websearch.run_websearch("查天氣")
