"""Tests for voice_bridge local-skill routing (exec-plan 007).

Verifies that local-skill utterances bypass the GPT streaming path and go
straight to the API, even when they don't contain search tokens.
"""
from src.api.skills.tokens import is_local_skill
from src.api.skills.policy import RouteKind
from src.bridge import voice_bridge


class TestLocalSkillDetection:
    def test_photoframe_phrases_route_local(self):
        assert is_local_skill("打開相框")
        assert is_local_skill("打開相簿")
        assert is_local_skill("打開照片")
        assert is_local_skill("open photoframe")

    def test_bunny_phrases_route_local(self):
        assert is_local_skill("切回兔兔")
        assert is_local_skill("打開兔兔")

    def test_chitchat_does_not_route_local(self):
        assert not is_local_skill("你好")
        assert not is_local_skill("今天幾號")
        assert not is_local_skill("你喜歡兔兔嗎")
        assert not is_local_skill("相框是什麼")
        assert not is_local_skill("")

    def test_wake_prefixed_bunny_command_stays_local(self):
        assert is_local_skill("兔兔助理切回兔兔")

    def test_voice_bridge_reexports_is_local_skill(self):
        # voice_bridge imports the helper — make sure the symbol exists.
        assert callable(voice_bridge.is_local_skill)
        assert voice_bridge.is_local_skill("打開相框") is True
        assert voice_bridge.is_local_skill("你好") is False

    def test_voice_bridge_imports_shared_classifier(self):
        decision = voice_bridge.classify_request("打開相框")

        assert decision.kind == RouteKind.LOCAL_SKILL
        assert decision.routed_text == "打開相框"

    def test_voice_bridge_classifies_time_query(self):
        decision = voice_bridge.classify_request("東京時間呢")
        assert decision.kind == RouteKind.TIME_QUERY
        assert decision.time_query is not None
        assert decision.time_query.timezone == "Asia/Tokyo"


class TestWakeStripperRecovery:
    """Regression: the fuzzy wake-word stripper can accidentally eat the
    bunny noun (e.g. variant '兔兔兔' fuzzy-matches a trailing '回兔兔'),
    leaving command='切回' which no longer trips is_local_skill.
    The bridge must check the RAW transcript as a fallback."""

    def test_command_lost_bunny_but_transcript_kept_it(self):
        command = "切回"  # what wake-stripper produced
        transcript = "兔兔助理切回兔兔"  # what STT actually heard
        assert not is_local_skill(command)
        assert is_local_skill(transcript)  # fallback path catches it

        decision = voice_bridge.classify_request(command, raw_transcript=transcript)
        assert decision.kind == RouteKind.LOCAL_SKILL
        assert decision.routed_text == transcript
        assert decision.used_raw_transcript is True
