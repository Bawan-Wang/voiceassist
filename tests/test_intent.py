"""
test_intent.py — unit tests for pure logic functions in bridge/voice_bridge.py

These tests do NOT start any services or touch audio devices.
"""
import sys
from pathlib import Path

# Make sure src/ is importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.api.skills.tokens import is_search_intent


class TestIsSearchIntent:
    @pytest.mark.parametrize("text,expected", [
        ("幫我查高雄天氣", True),
        ("今天天氣怎樣", True),
        ("搜尋最新新聞", True),
        ("找一下附近餐廳", True),
        ("你好", False),
        ("今天幾號", False),
        ("打開相框", False),
        ("切回兔兔", False),
    ])
    def test_search_tokens(self, text, expected):
        assert is_search_intent(text) == expected, f"is_search_intent({text!r}) should be {expected}"
