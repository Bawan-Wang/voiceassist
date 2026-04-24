"""
conftest.py — shared pytest fixtures for voiceassist tests.

Mocks out external calls so tests run fast without consuming API quota:
- subprocess.run  → mocks openclaw agent responses
- openai.OpenAI   → mocks OpenAI API responses
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openclaw_result(text: str) -> MagicMock:
    """Build a mock subprocess.CompletedProcess that looks like openclaw --json output."""
    payload = json.dumps({"payloads": [{"text": text, "mediaUrl": None}]})
    mock = MagicMock()
    mock.stdout = payload
    mock.stderr = ""
    mock.returncode = 0
    return mock


def _make_openai_response(text: str) -> MagicMock:
    """Build a mock OpenAI response object."""
    content = MagicMock()
    content.type = "output_text"
    content.text = text
    item = MagicMock()
    item.content = [content]
    resp = MagicMock()
    resp.output = [item]
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_openclaw():
    """Patch subprocess.run so openclaw returns a canned response."""
    with patch("src.api.app.subprocess.run") as mock_run:
        mock_run.return_value = _make_openclaw_result("這是測試回覆。")
        yield mock_run


@pytest.fixture
def mock_openai():
    """Patch OpenAI client so no real API calls are made.
    api.app uses 'from openai import OpenAI' inside functions (lazy import),
    so we patch the source module openai.OpenAI."""
    with patch("openai.OpenAI") as mock_cls:
        instance = MagicMock()
        instance.responses.create.return_value = _make_openai_response("這是OpenAI測試回覆。")
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def client(mock_openclaw, mock_openai):
    """FastAPI TestClient with all external calls mocked."""
    from src.api.app import app
    return TestClient(app)
