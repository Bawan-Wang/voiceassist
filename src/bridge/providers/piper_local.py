from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Optional

from piper.voice import PiperVoice

from .common import ensure_files
from .tts_base import TextToSpeechProvider

BASE_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = BASE_DIR / "models" / "piper"
MODEL_PATH = MODEL_DIR / "zh_CN-huayan-medium.onnx"
MODEL_CONFIG_PATH = MODEL_DIR / "zh_CN-huayan-medium.onnx.json"
MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
MODEL_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"


def _resolve_path(path_value: str | Path | None, default_path: Path) -> Path:
    if path_value is None:
        return default_path
    path = Path(path_value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


class PiperTextToSpeechProvider(TextToSpeechProvider):
    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        config_path: str | Path | None = None,
        model_url: Optional[str] = None,
        config_url: Optional[str] = None,
    ) -> None:
        self.model_path = _resolve_path(model_path, MODEL_PATH)
        self.model_config_path = _resolve_path(config_path, MODEL_CONFIG_PATH)
        self.model_url = model_url or MODEL_URL
        self.config_url = config_url or MODEL_CONFIG_URL
        ensure_files(
            (
                (self.model_url, self.model_path),
                (self.config_url, self.model_config_path),
            )
        )
        self.voice = PiperVoice.load(str(self.model_path))

    def synthesize_to_file(self, text: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        with wave.open(str(tmp_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.voice.config.sample_rate)
            self.voice.synthesize_wav(text, wav_file)
        return tmp_path
