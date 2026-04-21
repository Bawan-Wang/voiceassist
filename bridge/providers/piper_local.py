from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from piper.voice import PiperVoice

from .common import ensure_files
from .tts_base import TextToSpeechProvider

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "models" / "piper"
MODEL_PATH = MODEL_DIR / "zh_CN-huayan-medium.onnx"
MODEL_CONFIG_PATH = MODEL_DIR / "zh_CN-huayan-medium.onnx.json"
MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
MODEL_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"


class PiperTextToSpeechProvider(TextToSpeechProvider):
    def __init__(self) -> None:
        ensure_files(
            (
                (MODEL_URL, MODEL_PATH),
                (MODEL_CONFIG_URL, MODEL_CONFIG_PATH),
            )
        )
        self.voice = PiperVoice.load(str(MODEL_PATH))

    def synthesize_to_file(self, text: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        with wave.open(str(tmp_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.voice.config.sample_rate)
            self.voice.synthesize_wav(text, wav_file)
        return tmp_path
