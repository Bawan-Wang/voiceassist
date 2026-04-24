from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.yaml"

DEFAULT_VOICEBRIDGE_CONFIG: dict[str, Any] = {
    "state_path": "data/demo_state.json",
    "audio": {
        "sample_rate": 16000,
        "frame_ms": 30,
        "padding_ms": 600,
        "input_device": None,
        "playback_device": "plughw:2,0",
    },
    "wake": {
        "primary": "兔兔助理",
        "variants": [
            "兔兔助理",
            "兔兔助手",
            "兔兔兔",
            "兔兔",
            "bunny assistant",
            "bunny helper",
            "zero",
            "圖圖助理",
            "嘟嘟助理",
            "處處助理",
            "兔兔處理",
            "兔兔注意",
            "杜兔助理",
            "嘟兔助理",
            "圖兔助理",
        ],
        "follow_up_timeout_sec": 1.2,
        "auto_route_cooldown_sec": 2.0,
    },
    "routing": {
        "api_url": "http://127.0.0.1:8000/zero-assistant",
        "search_timeout_sec": 90,
        "llm_model": "gpt-4o-mini",
        "direct_max_tokens": 120,
        "stream_max_tokens": 120,
        "search_reply_max_tokens": 120,
        "search_hint": "好，我幫你查一下，請稍等。",
        "rewrite_search_reply_for_speech": True,
        "spoken_reply_timeout_sec": 12,
        "spoken_reply_max_input_chars": 1200,
    },
    "prompts": {
        "llm_system": "你是兔兔助理，一個友善的繁體中文語音助理。請用簡短的中文回答，不超過 30 個字，不使用 Markdown。",
        "spoken_reply": "你要把搜尋結果改寫成適合語音播報的繁體中文。規則：只保留重點、1到2句、不要網址、不要 Markdown、不要括號引用、不要條列、不要唸出奇怪符號，盡量口語自然。",
    },
    "text": {
        "trim_chars": " ，、。!?~'\"",
        "sentence_endings": "，,。！？!?；;：:\n",
        "stream_chunk_chars": 24,
        "search_tokens": [
            "查",
            "搜尋",
            "搜索",
            "找",
            "查詢",
            "查一下",
            "幫我查",
            "最新",
            "新聞",
            "網路上",
            "網頁",
            "資料",
            "天氣",
            "weather",
            "search",
            "look up",
            "find",
            "browse",
        ],
    },
    "vad": {
        "provider": "silero",
        "webrtc_aggressiveness": 2,
        "silero": {
            "model_path": "models/silero_vad.onnx",
            "model_url": "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
            "speech_threshold": 0.5,
            "silence_threshold": 0.2,
            "vote_window": 5,
            "vote_required": 3,
        },
    },
    "stt": {
        "active": "SherpaSenseVoice",
        "providers": {
            "SherpaSenseVoice": {
                "type": "sherpa_onnx_local",
                "model_path": "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/model.int8.onnx",
                "tokens_path": "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/tokens.txt",
                "model_url": "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/model.int8.onnx",
                "tokens_url": "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/tokens.txt",
                "num_threads": 2,
                "feature_dim": 80,
                "decoding_method": "greedy_search",
                "use_itn": True,
            }
        },
    },
    "tts": {
        "active": "PiperHuayan",
        "providers": {
            "PiperHuayan": {
                "type": "piper_local",
                "model_path": "models/piper/zh_CN-huayan-medium.onnx",
                "config_path": "models/piper/zh_CN-huayan-medium.onnx.json",
                "model_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx",
                "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json",
            }
        },
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_app_config(config_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = PROJECT_DIR / path

    loaded: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}

    merged = _deep_merge({"voiceBridge": DEFAULT_VOICEBRIDGE_CONFIG}, loaded)
    return path, merged


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def get_selected_provider(config: dict[str, Any], section_name: str) -> tuple[str, dict[str, Any]]:
    section = config.get(section_name, {})
    active_name = section.get("active")
    providers = section.get("providers", {})
    if not active_name:
        raise ValueError(f"voiceBridge.{section_name}.active is required")
    if active_name not in providers:
        raise ValueError(
            f"voiceBridge.{section_name}.active={active_name!r} not found in providers"
        )
    provider_config = dict(providers[active_name])
    provider_config.setdefault("name", active_name)
    return active_name, provider_config
