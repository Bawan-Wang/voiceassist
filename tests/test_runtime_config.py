"""
Tests for config-driven runtime selection in the voice bridge.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest
import yaml as _yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bridge.runtime_config import load_app_config
from src.bridge.voice_bridge import build_bridge_config, update_state

PROJECT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def _write_full_config(tmp_path: Path, **dotted_overrides) -> Path:
    """Copy the project's ``config.yaml`` into ``tmp_path`` and apply
    ``dotted.key=value`` overrides. Lets each test focus on the keys
    it cares about while satisfying the strict yaml requirement
    introduced by exec-plan 016.
    """
    target = tmp_path / "config.yaml"
    data = _yaml.safe_load(PROJECT_CONFIG.read_text(encoding="utf-8")) or {}
    for dotted, value in dotted_overrides.items():
        cur = data
        parts = dotted.split(".")
        for seg in parts[:-1]:
            cur = cur.setdefault(seg, {})
        cur[parts[-1]] = value
    target.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target


def test_build_bridge_config_uses_active_provider_selection(tmp_path):
    config_path = _write_full_config(
        tmp_path,
        **{
            "voiceBridge.audio.playback_device": "plughw:9,0",
            "voiceBridge.audio.input_device": 7,
            "voiceBridge.wake.primary": "測試助理",
            "voiceBridge.wake.variants": ["測試助理", "兔兔助理"],
            "voiceBridge.stt.active": "AltSherpa",
            "voiceBridge.stt.providers": {
                "SherpaSenseVoice": {
                    "type": "sherpa_onnx_local",
                    "model_path": "models/default-model.onnx",
                    "tokens_path": "models/default-tokens.txt",
                },
                "AltSherpa": {
                    "type": "sherpa_onnx_local",
                    "model_path": "models/alt-model.onnx",
                    "tokens_path": "models/alt-tokens.txt",
                },
            },
            "voiceBridge.tts.active": "AltPiper",
            "voiceBridge.tts.providers": {
                "PiperHuayan": {
                    "type": "piper_local",
                    "model_path": "models/default-voice.onnx",
                    "config_path": "models/default-voice.onnx.json",
                },
                "AltPiper": {
                    "type": "piper_local",
                    "model_path": "models/alt-voice.onnx",
                    "config_path": "models/alt-voice.onnx.json",
                },
            },
        },
    )

    _, app_config = load_app_config(config_path)
    voice_config = app_config["voiceBridge"]
    args = argparse.Namespace(
        config=str(config_path),
        input_device=None,
        playback_device="plughw:9,0",
        wake="測試助理",
    )

    cfg = build_bridge_config(voice_config, args)

    assert cfg.input_device == 7
    assert cfg.playback_device == "plughw:9,0"
    assert cfg.stt_provider_type == "sherpa_onnx_local"
    assert cfg.stt_provider_config["model_path"] == "models/alt-model.onnx"
    assert cfg.tts_provider_type == "piper_local"
    assert cfg.tts_provider_config["model_path"] == "models/alt-voice.onnx"
    assert cfg.wake_variants[0] == "測試助理"


def test_build_bridge_config_populates_runtime_strings(tmp_path):
    config_path = _write_full_config(
        tmp_path,
        **{
            "voiceBridge.routing.llm_model": "gpt-4-test",
            "voiceBridge.prompts.llm_system": "test system prompt",
            "voiceBridge.prompts.spoken_reply": "test spoken prompt",
            "voiceBridge.text.trim_chars": "_",
            "voiceBridge.text.sentence_endings": ".",
            "voiceBridge.text.stream_chunk_chars": 7,
        },
    )
    _, app_config = load_app_config(config_path)
    args = argparse.Namespace(
        config=str(config_path),
        input_device=None,
        playback_device=None,
        wake=None,
    )
    cfg = build_bridge_config(app_config["voiceBridge"], args)
    assert cfg.llm_model == "gpt-4-test"
    assert cfg.llm_system_prompt == "test system prompt"
    assert cfg.spoken_reply_prompt == "test spoken prompt"
    assert cfg.trim_chars == "_"
    assert cfg.sentence_endings == "."
    assert cfg.stream_chunk_chars == 7


def test_load_app_config_strict_missing_key_raises(tmp_path):
    config_path = _write_full_config(tmp_path)
    data = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
    del data["voiceBridge"]["routing"]["api_url"]
    config_path.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    _, app_config = load_app_config(config_path)
    args = argparse.Namespace(
        config=str(config_path),
        input_device=None,
        playback_device=None,
        wake=None,
    )
    with pytest.raises(ValueError, match="api_url"):
        build_bridge_config(app_config["voiceBridge"], args)


def test_load_app_config_missing_voiceBridge_top_key_raises(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("display:\n  width: 800\n", encoding="utf-8")
    with pytest.raises(ValueError, match="voiceBridge"):
        load_app_config(config_path)


def test_update_state_round_trip(tmp_path):
    import json

    state_path = tmp_path / "state.json"
    update_state(state_path, "listening", user_text="hi", assistant_text="hello")
    payload = json.loads(state_path.read_text())
    assert payload["phase"] == "listening"
    assert payload["userText"] == "hi"
    assert payload["assistantText"] == "hello"
    assert "lastUpdate" in payload
