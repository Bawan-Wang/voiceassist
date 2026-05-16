from datetime import datetime
from zoneinfo import ZoneInfo

from src.api.skills.time_query import TimeQueryIntent, parse_time_query, render_time_query_reply


class TestTimeQueryParser:
    def test_parse_local_time_query(self):
        intent = parse_time_query("現在幾點")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone == "Asia/Taipei"

    def test_parse_named_timezone_query(self):
        intent = parse_time_query("日本現在幾點")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone == "Asia/Tokyo"

    def test_parse_simplified_local_time_query(self):
        intent = parse_time_query("请问现在几点")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone == "Asia/Taipei"

    def test_parse_simplified_named_timezone_query(self):
        intent = parse_time_query("东京现在几点")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone == "Asia/Tokyo"

    def test_non_time_text_returns_none(self):
        assert parse_time_query("幫我查台北天氣") is None
        assert parse_time_query("你好") is None

    def test_unknown_place_requires_clarification(self):
        intent = parse_time_query("巴黎現在幾點")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone is None
        assert intent.label == "巴黎"
        assert intent.needs_clarification is True

    def test_unknown_place_natural_phrase_requires_clarification(self):
        intent = parse_time_query("幫我看一下巴黎時間")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone is None
        assert intent.label == "巴黎"

    def test_simplified_unknown_place_requires_clarification(self):
        intent = parse_time_query("巴黎现在几点")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone is None
        assert intent.label == "巴黎"

    def test_wake_prefixed_simplified_time_query_stays_local(self):
        intent = parse_time_query("兔助理，请问现在几点")
        assert intent is not None
        assert intent.kind == "time"
        assert intent.timezone == "Asia/Taipei"


class TestTimeQueryRenderer:
    def test_render_time_local(self):
        now = datetime(2026, 5, 16, 9, 20, tzinfo=ZoneInfo("Asia/Taipei"))
        intent = TimeQueryIntent(kind="time", timezone="Asia/Taipei", label="台灣")
        reply = render_time_query_reply(intent, now=now)
        assert "現在時間是" in reply
        assert "9點20分" in reply

    def test_render_time_foreign_timezone_mentions_place(self):
        now = datetime(2026, 5, 16, 20, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        intent = TimeQueryIntent(kind="time", timezone="Asia/Tokyo", label="日本")
        reply = render_time_query_reply(intent, now=now)
        assert "日本現在時間是" in reply
        assert "8點整" in reply

    def test_render_unknown_place_returns_clarification(self):
        intent = TimeQueryIntent(kind="time", timezone=None, label="巴黎", needs_clarification=True)
        reply = render_time_query_reply(intent)
        assert reply == "抱歉，巴黎的時區我還不確定，你可以換個地名說法嗎？"
