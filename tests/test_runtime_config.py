"""
Tests for config-driven runtime selection in the voice bridge.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bridge.runtime_config import load_app_config
from src.bridge.voice_bridge import build_bridge_config, update_state


def test_build_bridge_config_uses_active_provider_selection(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
voiceBridge:
  audio:
    playback_device: plughw:9,0
    input_device: 7
  wake:
    primary: 測試助理
    variants: [測試助理, 兔兔助理]
  stt:
    active: AltSherpa
    providers:
      SherpaSenseVoice:
        type: sherpa_onnx_local
        model_path: models/default-model.onnx
        tokens_path: models/default-tokens.txt
      AltSherpa:
        type: sherpa_onnx_local
        model_path: models/alt-model.onnx
        tokens_path: models/alt-tokens.txt
  tts:
    active: AltPiper
    providers:
      PiperHuayan:
        type: piper_local
        model_path: models/default-voice.onnx
        config_path: models/default-voice.onnx.json
      AltPiper:
        type: piper_local
        model_path: models/alt-voice.onnx
        config_path: models/alt-voice.onnx.json
""",
        encoding="utf-8",
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
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
voiceBridge:
  routing:
    llm_model: gpt-4-test
  prompts:
    llm_system: "test system prompt"
    spoken_reply: "test spoken prompt"
  text:
    trim_chars: "_"
    sentence_endings: "."
    stream_chunk_chars: 7
""",
        encoding="utf-8",
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


def test_update_state_round_trip(tmp_path):
    import json

    state_path = tmp_path / "state.json"
    update_state(state_path, "listening", user_text="hi", assistant_text="hello")
    payload = json.loads(state_path.read_text())
    assert payload["phase"] == "listening"
    assert payload["userText"] == "hi"
    assert payload["assistantText"] == "hello"
    assert "lastUpdate" in payload
