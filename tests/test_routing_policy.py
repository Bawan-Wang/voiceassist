"""Tests for the shared routing policy introduced in exec-plan 020."""
from src.api.skills import open_bunny, open_photoframe
from src.api.skills.policy import RouteKind, classify_request


class TestRoutingPolicy:
    def test_search_token_plus_bunny_topic_stays_search(self):
        decision = classify_request("幫我查兔兔")

        assert decision.kind == RouteKind.TOOL_NEEDED
        assert decision.skill is None
        assert decision.routed_text == "幫我查兔兔"
        assert decision.is_search is True
        assert decision.used_raw_transcript is False

    def test_search_becomes_tool_needed(self):
        decision = classify_request("幫我查新北天氣")

        assert decision.kind == RouteKind.TOOL_NEEDED
        assert decision.skill is None
        assert decision.routed_text == "幫我查新北天氣"
        assert decision.is_search is True
        assert decision.used_raw_transcript is False

    def test_time_query_becomes_time_query_route(self):
        decision = classify_request("日本現在幾點")

        assert decision.kind == RouteKind.TIME_QUERY
        assert decision.time_query is not None
        assert decision.time_query.timezone == "Asia/Tokyo"
        assert decision.routed_text == "日本現在幾點"

    def test_simplified_time_query_becomes_time_query_route(self):
        decision = classify_request("请问现在几点")

        assert decision.kind == RouteKind.TIME_QUERY
        assert decision.time_query is not None
        assert decision.time_query.timezone == "Asia/Taipei"

    def test_chat_becomes_chat(self):
        decision = classify_request("你好")

        assert decision.kind == RouteKind.CHAT
        assert decision.skill is None
        assert decision.routed_text == "你好"
        assert decision.is_search is False
        assert decision.used_raw_transcript is False

    def test_raw_transcript_fallback_catches_wake_strip_case(self):
        decision = classify_request("切回", raw_transcript="兔兔助理切回兔兔")

        assert decision.kind == RouteKind.LOCAL_SKILL
        assert decision.skill is open_bunny
        assert decision.routed_text == "兔兔助理切回兔兔"
        assert decision.used_raw_transcript is True

    def test_photoframe_phrase_routes_to_local_skill(self):
        decision = classify_request("打開相框")

        assert decision.kind == RouteKind.LOCAL_SKILL
        assert decision.skill is open_photoframe
        assert decision.routed_text == "打開相框"

    def test_bunny_topic_chitchat_stays_chat(self):
        decision = classify_request("你喜歡兔兔嗎")

        assert decision.kind == RouteKind.CHAT
        assert decision.skill is None

    def test_photoframe_topic_chitchat_stays_chat(self):
        decision = classify_request("我想看照片展")

        assert decision.kind == RouteKind.CHAT
        assert decision.skill is None

    def test_reminder_with_timezone_routes_before_time_query(self):
        decision = classify_request("日本時間下午三點提醒我開會")

        assert decision.kind == RouteKind.REMINDER
        assert decision.time_query is None

    def test_reminder_with_search_word_stays_reminder(self):
        decision = classify_request("明天早上八點提醒我查資料")

        assert decision.kind == RouteKind.REMINDER
        assert decision.is_search is False

    def test_invalid_reminder_still_routes_to_reminder_path(self):
        decision = classify_request("提醒我買牛奶")

        assert decision.kind == RouteKind.REMINDER
