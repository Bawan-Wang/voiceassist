from __future__ import annotations

from pathlib import Path

import numpy as np
import sherpa_onnx

from .asr_base import SpeechToTextProvider
from .common import ensure_files

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
MODEL_PATH = MODEL_DIR / "model.int8.onnx"
TOKENS_PATH = MODEL_DIR / "tokens.txt"
MODEL_URL = "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/model.int8.onnx"
TOKENS_URL = "https://modelscope.cn/models/pengzhendong/sherpa-onnx-sense-voice-zh-en-ja-ko-yue/resolve/master/tokens.txt"


class SherpaOnnxSpeechToTextProvider(SpeechToTextProvider):
    def __init__(self, sample_rate: int = 16_000) -> None:
        self.sample_rate = sample_rate
        ensure_files(
            (
                (MODEL_URL, MODEL_PATH),
                (TOKENS_URL, TOKENS_PATH),
            )
        )
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(MODEL_PATH),
            tokens=str(TOKENS_PATH),
            num_threads=2,
            sample_rate=sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
            debug=False,
            use_itn=True,
        )

    def transcribe(self, audio_bytes: bytes) -> str:
        stream = self.recognizer.create_stream()
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        stream.accept_waveform(self.sample_rate, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()
