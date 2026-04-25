"""Tests for voice_bridge local-skill routing (exec-plan 007).

Verifies that local-skill utterances bypass the GPT streaming path and go
straight to the API, even when they don't contain search tokens.
"""
from src.api.skills.tokens import is_local_skill
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
        assert not is_local_skill("")

    def test_voice_bridge_reexports_is_local_skill(self):
        # voice_bridge imports the helper — make sure the symbol exists.
        assert callable(voice_bridge.is_local_skill)
        assert voice_bridge.is_local_skill("打開相框") is True
        assert voice_bridge.is_local_skill("你好") is False


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
