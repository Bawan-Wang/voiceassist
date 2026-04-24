from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import sherpa_onnx

from .asr_base import SpeechToTextProvider
from .common import ensure_files

BASE_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = BASE_DIR / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
MODEL_PATH = MODEL_DIR / "model.int8.onnx"
TOKENS_PATH = MODEL_DIR / "tokens.txt"
MODEL_URL = "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/model.int8.onnx"
TOKENS_URL = "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/tokens.txt"


def _resolve_path(path_value: str | Path | None, default_path: Path) -> Path:
    if path_value is None:
        return default_path
    path = Path(path_value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


class SherpaOnnxSpeechToTextProvider(SpeechToTextProvider):
    def __init__(
        self,
        sample_rate: int = 16_000,
        *,
        model_path: str | Path | None = None,
        tokens_path: str | Path | None = None,
        model_url: Optional[str] = None,
        tokens_url: Optional[str] = None,
        num_threads: int = 2,
        feature_dim: int = 80,
        decoding_method: str = "greedy_search",
        use_itn: bool = True,
    ) -> None:
        self.sample_rate = sample_rate
        self.model_path = _resolve_path(model_path, MODEL_PATH)
        self.tokens_path = _resolve_path(tokens_path, TOKENS_PATH)
        self.model_url = model_url or MODEL_URL
        self.tokens_url = tokens_url or TOKENS_URL
        ensure_files(
            (
                (self.model_url, self.model_path),
                (self.tokens_url, self.tokens_path),
            )
        )
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(self.model_path),
            tokens=str(self.tokens_path),
            num_threads=num_threads,
            sample_rate=sample_rate,
            feature_dim=feature_dim,
            decoding_method=decoding_method,
            debug=False,
            use_itn=use_itn,
        )

    def transcribe(self, audio_bytes: bytes) -> str:
        stream = self.recognizer.create_stream()
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        stream.accept_waveform(self.sample_rate, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()
