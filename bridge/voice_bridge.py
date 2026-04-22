#!/usr/bin/env python3
"""Audio bridge that lets Zero listen + speak with a hybrid local/cloud pipeline.

Workflow:
1. Continuously listens to the USB speakerphone microphone.
2. Uses Silero VAD (fallback: WebRTC VAD) to segment utterances.
3. Runs local Sherpa-ONNX STT to get text.
4. Requires the wake phrase "兔兔助理" ("Bunny assistant") before acting.
5. Sends the command to an LLM (gpt-4o-mini) to craft a short reply.
6. Uses local Piper TTS to synthesize speech sentence-by-sentence.
7. Continuously updates data/demo_state.json so the PyGame bunny reacts.

Set OPENAI_API_KEY in your environment before running this script for General Q&A.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import difflib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Deque, Optional

import numpy as np
import onnxruntime
import sounddevice as sd
import webrtcvad
from openai import OpenAI

try:
    from bridge.providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider
    from bridge.runtime_config import get_selected_provider, load_app_config, resolve_project_path
except ModuleNotFoundError:
    from providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider
    from runtime_config import get_selected_provider, load_app_config, resolve_project_path

BASE_DIR = Path(__file__).parent.parent  # repo root (voiceassist/)
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "data" / "demo_state.json"
SILERO_MODEL_PATH = BASE_DIR / "models" / "silero_vad.onnx"
SILERO_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
DEFAULT_WAKE = "兔兔助理"
DEFAULT_PLAYBACK = "plughw:2,0"
LLM_MODEL = "gpt-4o-mini"
API_URL = "http://127.0.0.1:8000/zero-assistant"
SEARCH_TIMEOUT_SEC = 90
DIRECT_MAX_TOKENS = 120
STREAM_MAX_TOKENS = 120
SEARCH_REPLY_MAX_TOKENS = 120
TRIM_CHARS = " ，、。!?~'\""
SENTENCE_ENDINGS = "，,。！？!?；;：:\n"
STREAM_CHUNK_CHARS = 24
LLM_SYSTEM_PROMPT = (
    "你是兔兔助理，一個友善的繁體中文語音助理。"
    "請用簡短的中文回答，不超過 30 個字，不使用 Markdown。"
)
SPOKEN_REPLY_PROMPT = (
    "你要把搜尋結果改寫成適合語音播報的繁體中文。"
    "規則：只保留重點、1到2句、不要網址、不要 Markdown、不要括號引用、"
    "不要條列、不要唸出奇怪符號，盡量口語自然。"
)
SEARCH_HINT = "好，我幫你查一下，請稍等。"


@dataclass
class BridgeConfig:
    sample_rate: int = 16_000
    frame_ms: int = 30
    padding_ms: int = 600
    input_device: Optional[int] = None
    playback_device: str = DEFAULT_PLAYBACK
    pending_wake_timeout_sec: float = 1.2
    auto_route_cooldown_sec: float = 2.0
    webrtc_aggressiveness: int = 2
    silero_speech_threshold: float = 0.5
    silero_silence_threshold: float = 0.2
    silero_vote_window: int = 5
    silero_vote_required: int = 3
    search_timeout_sec: int = SEARCH_TIMEOUT_SEC
    direct_max_tokens: int = DIRECT_MAX_TOKENS
    stream_max_tokens: int = STREAM_MAX_TOKENS
    search_reply_max_tokens: int = SEARCH_REPLY_MAX_TOKENS
    rewrite_search_reply_for_speech: bool = True
    spoken_reply_timeout_sec: int = 12
    spoken_reply_max_input_chars: int = 1200
    search_hint: str = SEARCH_HINT
    api_url: str = API_URL
    stt_provider_type: str = "sherpa_onnx_local"
    stt_provider_config: dict[str, Any] = field(default_factory=dict)
    tts_provider_type: str = "piper_local"
    tts_provider_config: dict[str, Any] = field(default_factory=dict)
    wake_variants: tuple[str, ...] = (
        "兔兔助理", "兔兔助手", "兔兔兔", "兔兔", "bunny assistant", "bunny helper", "zero",
        # 常見誤辨容錯
        "圖圖助理", "嘟嘟助理", "處處助理", "兔兔處理", "兔兔注意", "杜兔助理", "嘟兔助理", "圖兔助理",
    )


_SEARCH_TOKENS = (
    "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
    "網路上", "網頁", "資料", "天氣", "weather", "search", "look up", "find", "browse",
)


def is_search_intent(text: str) -> bool:
    """Return True if the command looks like a search/browse request."""
    return any(tok in text for tok in _SEARCH_TOKENS)


def ensure_silero_model(model_path: Path, model_url: str) -> Optional[Path]:
    """Ensure the Silero VAD model exists locally, downloading it on first use."""
    if model_path.exists():
        return model_path

    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = model_path.with_suffix(".onnx.tmp")
        print(f"[voice_bridge] Silero model missing; downloading from {model_url}")
        urllib.request.urlretrieve(model_url, tmp_path)
        tmp_path.replace(model_path)
        print(f"[voice_bridge] Silero model downloaded to {model_path}")
        return model_path
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[voice_bridge] Silero model download failed: {exc}")
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # pylint: disable=broad-except
            pass
        return None


class _SileroVADState:
    def __init__(self, vote_window: int) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.audio_buffer = bytearray()
        self.voice_window: Deque[bool] = collections.deque(maxlen=vote_window)
        self.last_is_voice = False


def apply_runtime_config(app_config: dict[str, Any]) -> dict[str, Any]:
    global STATE_PATH, SILERO_MODEL_PATH, SILERO_MODEL_URL
    global DEFAULT_WAKE, DEFAULT_PLAYBACK, LLM_MODEL, API_URL
    global SEARCH_TIMEOUT_SEC, DIRECT_MAX_TOKENS, STREAM_MAX_TOKENS, SEARCH_REPLY_MAX_TOKENS
    global TRIM_CHARS, SENTENCE_ENDINGS, STREAM_CHUNK_CHARS
    global LLM_SYSTEM_PROMPT, SPOKEN_REPLY_PROMPT, SEARCH_HINT, _SEARCH_TOKENS

    voice_config = app_config.get("voiceBridge", {})
    audio = voice_config.get("audio", {})
    wake = voice_config.get("wake", {})
    routing = voice_config.get("routing", {})
    prompts = voice_config.get("prompts", {})
    text_cfg = voice_config.get("text", {})
    vad = voice_config.get("vad", {})
    silero = vad.get("silero", {})

    STATE_PATH = resolve_project_path(voice_config.get("state_path", STATE_PATH))
    SILERO_MODEL_PATH = resolve_project_path(silero.get("model_path", SILERO_MODEL_PATH))
    SILERO_MODEL_URL = silero.get("model_url", SILERO_MODEL_URL)
    DEFAULT_WAKE = wake.get("primary", DEFAULT_WAKE)
    DEFAULT_PLAYBACK = audio.get("playback_device", DEFAULT_PLAYBACK)
    LLM_MODEL = routing.get("llm_model", LLM_MODEL)
    API_URL = routing.get("api_url", API_URL)
    SEARCH_TIMEOUT_SEC = int(routing.get("search_timeout_sec", SEARCH_TIMEOUT_SEC))
    DIRECT_MAX_TOKENS = int(routing.get("direct_max_tokens", DIRECT_MAX_TOKENS))
    STREAM_MAX_TOKENS = int(routing.get("stream_max_tokens", STREAM_MAX_TOKENS))
    SEARCH_REPLY_MAX_TOKENS = int(routing.get("search_reply_max_tokens", SEARCH_REPLY_MAX_TOKENS))
    TRIM_CHARS = text_cfg.get("trim_chars", TRIM_CHARS)
    SENTENCE_ENDINGS = text_cfg.get("sentence_endings", SENTENCE_ENDINGS)
    STREAM_CHUNK_CHARS = int(text_cfg.get("stream_chunk_chars", STREAM_CHUNK_CHARS))
    LLM_SYSTEM_PROMPT = prompts.get("llm_system", LLM_SYSTEM_PROMPT)
    SPOKEN_REPLY_PROMPT = prompts.get("spoken_reply", SPOKEN_REPLY_PROMPT)
    SEARCH_HINT = routing.get("search_hint", SEARCH_HINT)
    _SEARCH_TOKENS = tuple(text_cfg.get("search_tokens", list(_SEARCH_TOKENS)))

    return voice_config


def build_bridge_config(voice_config: dict[str, Any], args: argparse.Namespace) -> BridgeConfig:
    audio = voice_config.get("audio", {})
    wake = voice_config.get("wake", {})
    routing = voice_config.get("routing", {})
    vad = voice_config.get("vad", {})
    silero = vad.get("silero", {})
    _, stt_provider = get_selected_provider(voice_config, "stt")
    _, tts_provider = get_selected_provider(voice_config, "tts")

    input_device = args.input_device if args.input_device is not None else audio.get("input_device")
    playback_device = args.playback_device or audio.get("playback_device", DEFAULT_PLAYBACK)

    cfg = BridgeConfig(
        sample_rate=int(audio.get("sample_rate", 16000)),
        frame_ms=int(audio.get("frame_ms", 30)),
        padding_ms=int(audio.get("padding_ms", 600)),
        input_device=input_device,
        playback_device=playback_device,
        pending_wake_timeout_sec=float(wake.get("follow_up_timeout_sec", 1.2)),
        auto_route_cooldown_sec=float(wake.get("auto_route_cooldown_sec", 2.0)),
        webrtc_aggressiveness=int(vad.get("webrtc_aggressiveness", 2)),
        silero_speech_threshold=float(silero.get("speech_threshold", 0.5)),
        silero_silence_threshold=float(silero.get("silence_threshold", 0.2)),
        silero_vote_window=int(silero.get("vote_window", 5)),
        silero_vote_required=int(silero.get("vote_required", 3)),
        search_timeout_sec=int(routing.get("search_timeout_sec", SEARCH_TIMEOUT_SEC)),
        direct_max_tokens=int(routing.get("direct_max_tokens", DIRECT_MAX_TOKENS)),
        stream_max_tokens=int(routing.get("stream_max_tokens", STREAM_MAX_TOKENS)),
        search_reply_max_tokens=int(routing.get("search_reply_max_tokens", SEARCH_REPLY_MAX_TOKENS)),
        rewrite_search_reply_for_speech=bool(routing.get("rewrite_search_reply_for_speech", True)),
        spoken_reply_timeout_sec=int(routing.get("spoken_reply_timeout_sec", 12)),
        spoken_reply_max_input_chars=int(routing.get("spoken_reply_max_input_chars", 1200)),
        search_hint=str(routing.get("search_hint", SEARCH_HINT)),
        api_url=str(routing.get("api_url", API_URL)),
        stt_provider_type=str(stt_provider.get("type", "sherpa_onnx_local")),
        stt_provider_config={key: value for key, value in stt_provider.items() if key not in {"type", "name"}},
        tts_provider_type=str(tts_provider.get("type", "piper_local")),
        tts_provider_config={key: value for key, value in tts_provider.items() if key not in {"type", "name"}},
        wake_variants=tuple(wake.get("variants", BridgeConfig.wake_variants)),
    )
    if args.wake:
        cfg.wake_variants = tuple(dict.fromkeys((args.wake, *cfg.wake_variants)))
    return cfg


class VoiceBridge:
    def __init__(self, cfg: BridgeConfig, client: OpenAI) -> None:
        self.cfg = cfg
        self.client = client
        self.stt_provider = self._create_stt_provider()
        self.tts_provider = self._create_tts_provider()
        self.webrtc_vad = webrtcvad.Vad(cfg.webrtc_aggressiveness)
        self.frame_bytes = int(cfg.sample_rate * cfg.frame_ms / 1000) * 2  # 16-bit mono
        self.padding_frames = cfg.padding_ms // cfg.frame_ms
        self._running = True
        self._pending_wake_until: Optional[datetime] = None
        self._last_auto_command_ts = 0.0
        self._silero_session: Optional[onnxruntime.InferenceSession] = None

        silero_model_path = ensure_silero_model(SILERO_MODEL_PATH, SILERO_MODEL_URL)
        if silero_model_path is not None and silero_model_path.exists():
            try:
                opts = onnxruntime.SessionOptions()
                opts.inter_op_num_threads = 1
                opts.intra_op_num_threads = 1
                self._silero_session = onnxruntime.InferenceSession(
                    str(silero_model_path),
                    providers=["CPUExecutionProvider"],
                    sess_options=opts,
                )
                print(f"[voice_bridge] Using Silero VAD: {silero_model_path}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[voice_bridge] Silero VAD init failed, fallback to WebRTC: {exc}")

    def _create_stt_provider(self) -> SherpaOnnxSpeechToTextProvider:
        provider_type = self.cfg.stt_provider_type.lower()
        if provider_type == "sherpa_onnx_local":
            return SherpaOnnxSpeechToTextProvider(
                sample_rate=self.cfg.sample_rate,
                **self.cfg.stt_provider_config,
            )
        raise ValueError(f"Unsupported STT provider type: {self.cfg.stt_provider_type}")

    def _create_tts_provider(self) -> PiperTextToSpeechProvider:
        provider_type = self.cfg.tts_provider_type.lower()
        if provider_type == "piper_local":
            return PiperTextToSpeechProvider(**self.cfg.tts_provider_config)
        raise ValueError(f"Unsupported TTS provider type: {self.cfg.tts_provider_type}")

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)
        sd.default.samplerate = self.cfg.sample_rate
        sd.default.channels = 1
        sd.default.dtype = "int16"
        if self.cfg.input_device is not None:
            sd.default.device = (self.cfg.input_device, None)

        print("[voice_bridge] Ready. Say '兔兔助理 ...' to wake up Zero.")
        while self._running:
            audio = self._capture_utterance()
            if not audio:
                continue

            update_state("listening", user_text="……", assistant_text="Zero 正在傾聽中…")
            transcript = self.transcribe(audio)
            if not transcript:
                update_state("idle")
                continue

            matched = self._match_wake_phrase(transcript)

            # Support two-step wake: say wake word first, then command shortly after.
            now = datetime.now(timezone.utc)
            if matched:
                command = transcript.split(matched, 1)[1] if matched in transcript else transcript
                command = command.lstrip(TRIM_CHARS).strip()
                if not command:
                    command = transcript.replace(matched, '', 1).strip()
                if not command:
                    self._pending_wake_until = now + timedelta(seconds=self.cfg.pending_wake_timeout_sec)
                    print("[voice_bridge] Wake word heard; waiting for next sentence as command")
                    update_state("listening", user_text="請說指令", assistant_text="")
                    continue
            else:
                if self._pending_wake_until and now <= self._pending_wake_until:
                    command = transcript.strip()
                    self._pending_wake_until = None
                    print("[voice_bridge] Using follow-up sentence as command")
                else:
                    self._pending_wake_until = None
                    if self._should_route_without_wake(transcript):
                        command = transcript.strip()
                        print("[voice_bridge] Auto-route (no explicit wake word)")
                    else:
                        print(f"[voice_bridge] Ignored (no wake word): {transcript}")
                        update_state("idle")
                        continue
            print(f"[voice_bridge] Command: {command}")

            searching = is_search_intent(command)
            if searching:
                hint = self.cfg.search_hint
                print(f"[voice_bridge] Search intent detected, speaking hint first")
                update_state("thinking", user_text=command, assistant_text=hint)
                self.speak(hint)
                reply = self.generate_reply(command, search=True)
                if not reply:
                    update_state("idle", assistant_text="抱歉，沒有聽清楚。")
                    continue

                spoken_reply = self._prepare_reply_for_speech(reply, search=True)
                update_state("speaking", assistant_text=reply)
                self.speak(spoken_reply)
            else:
                update_state("thinking", user_text=command, assistant_text="正在思考回覆…")

                reply = self.stream_reply_and_speak(command)
                if not reply:
                    update_state("idle", assistant_text="抱歉，沒有聽清楚。")
                    continue

            update_state("idle", assistant_text=reply)

    def _handle_stop(self, *_: object) -> None:
        self._running = False

    def _match_wake_phrase(self, transcript: str) -> Optional[str]:
        lower = transcript.lower()

        # 1) Exact/contains matching first
        for phrase in self.cfg.wake_variants:
            if phrase in transcript or phrase.lower() in lower:
                return phrase

        # 2) Token-combo fallback: loose matching for variants like "突突助理/處處住裡"
        compact = ''.join(ch for ch in transcript if ch.strip())
        rabbit_tokens = ("兔", "圖", "嘟", "突", "處", "臭", "杜", "tu", "tutu")
        helper_tokens = ("助理", "助手", "處理", "住裡", "注意", "zhuli", "zhu li")
        if any(t in compact.lower() for t in rabbit_tokens) and any(t in compact.lower() for t in helper_tokens):
            return "<token-combo-wake>"

        # 3) Fuzzy match for short Chinese misrecognitions (e.g., 圖圖助理/嘟嘟助理/處處助理)
        for phrase in self.cfg.wake_variants:
            p = ''.join(ch for ch in phrase if ch.strip())
            if len(p) < 3:
                continue
            for size in (max(3, len(p)-1), len(p), len(p)+1):
                if size <= 0 or len(compact) < size:
                    continue
                for i in range(0, len(compact) - size + 1):
                    chunk = compact[i:i+size]
                    ratio = difflib.SequenceMatcher(a=p, b=chunk).ratio()
                    if ratio >= 0.70:
                        return chunk
        return None

    def _should_route_without_wake(self, transcript: str) -> bool:
        """Semi-wake mode: route commands even without explicit wake word.
        Guard rails reduce accidental triggers."""
        t = transcript.strip()
        if not t:
            return False

        now_ts = time.time()
        # Cooldown to avoid rapid accidental fire
        if now_ts - self._last_auto_command_ts < self.cfg.auto_route_cooldown_sec:
            return False

        # If sentence looks command-like, always route
        lower = t.lower()
        command_tokens = (
            "幫我", "請", "可以", "能不能", "打開", "開啟", "切回", "關閉", "查", "查詢", "天氣", "多少", "怎麼", "為什麼",
            "help", "open", "close", "switch", "weather", "what", "how"
        )
        if any(tok in t for tok in command_tokens) or any(tok in lower for tok in command_tokens):
            self._last_auto_command_ts = now_ts
            return True

        # Fallback: medium-length spoken phrase (reduce noise)
        if len(t) >= 8:
            self._last_auto_command_ts = now_ts
            return True

        return False

    def _capture_utterance(self) -> bytes:
        """Stream microphone audio until VAD thinks the utterance ended."""
        ring_buffer: Deque[tuple[bytes, bool]] = collections.deque(maxlen=self.padding_frames)
        voiced_frames: list[bytes] = []
        triggered = False
        last_voice = time.time()
        silero_state = _SileroVADState(self.cfg.silero_vote_window) if self._silero_session is not None else None

        with sd.RawInputStream(blocksize=self.frame_bytes // 2, device=self.cfg.input_device) as stream:
            while self._running:
                frame, _ = stream.read(self.frame_bytes // 2)
                if not frame:
                    continue
                pcm_bytes = bytes(frame)
                is_speech = self._frame_has_speech(pcm_bytes, silero_state)

                if not triggered:
                    ring_buffer.append((pcm_bytes, is_speech))
                    num_voiced = len([f for f, speech in ring_buffer if speech])
                    if num_voiced > 0.8 * ring_buffer.maxlen:
                        triggered = True
                        last_voice = time.time()
                        voiced_frames.extend(f for f, _ in ring_buffer)
                        ring_buffer.clear()
                else:
                    voiced_frames.append(pcm_bytes)
                    ring_buffer.append((pcm_bytes, is_speech))
                    if is_speech:
                        last_voice = time.time()
                    elif time.time() - last_voice > self.cfg.padding_ms / 1000:
                        audio = b"".join(voiced_frames)
                        if audio:
                            return audio
                        voiced_frames = []
                        triggered = False
                        ring_buffer.clear()

        return b""

    def _frame_has_speech(self, pcm_bytes: bytes, silero_state: Optional[_SileroVADState]) -> bool:
        if self._silero_session is None or silero_state is None:
            return self.webrtc_vad.is_speech(pcm_bytes, self.cfg.sample_rate)

        silero_state.audio_buffer.extend(pcm_bytes)
        detected_voice = silero_state.last_is_voice
        while len(silero_state.audio_buffer) >= 512 * 2:
            chunk = bytes(silero_state.audio_buffer[: 512 * 2])
            del silero_state.audio_buffer[: 512 * 2]

            audio_int16 = np.frombuffer(chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_input = np.concatenate(
                [silero_state.context, audio_float32.reshape(1, -1)], axis=1
            ).astype(np.float32)
            ort_inputs = {
                "input": audio_input,
                "state": silero_state.state,
                "sr": np.array(16000, dtype=np.int64),
            }
            out, state = self._silero_session.run(None, ort_inputs)
            silero_state.state = state
            silero_state.context = audio_input[:, -64:]
            speech_prob = float(out.item())

            if speech_prob >= self.cfg.silero_speech_threshold:
                is_voice = True
            elif speech_prob <= self.cfg.silero_silence_threshold:
                is_voice = False
            else:
                is_voice = silero_state.last_is_voice

            silero_state.last_is_voice = is_voice
            silero_state.voice_window.append(is_voice)
            detected_voice = silero_state.voice_window.count(True) >= self.cfg.silero_vote_required

        return detected_voice

    def transcribe(self, audio_bytes: bytes) -> str:
        try:
            text = self.stt_provider.transcribe(audio_bytes)
            print(f"[voice_bridge] STT: {text}")
            return text
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] STT error: {exc}")
            return ""

    def generate_reply(self, prompt: str, search: bool = False) -> str:
        """Route prompt per spec:
          search=True  → local /zero-assistant API (OpenClaw Agent, timeout 90s)
          search=False → direct OpenAI GPT-4o-mini call
        """
        if search:
            return self._reply_via_api(prompt)
        return self._reply_via_gpt4o_mini(prompt)

    def _reply_via_api(self, prompt: str) -> str:
        """POST to local /zero-assistant (OpenClaw Agent) for search/browse."""
        import requests
        try:
            resp = requests.post(self.cfg.api_url, json={"text": prompt}, timeout=self.cfg.search_timeout_sec)
            resp.raise_for_status()
            result = (resp.json().get("reply_text") or "").strip()
            print(f"[voice_bridge] API reply: {result[:80]}{'...' if len(result)>80 else ''}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] API error: {exc}")
            return ""

    def _reply_via_gpt4o_mini(self, prompt: str) -> str:
        """Call GPT-4o-mini directly for general Q&A."""
        try:
            resp = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": LLM_SYSTEM_PROMPT,
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.cfg.direct_max_tokens,
            )
            result = (resp.choices[0].message.content or "").strip()
            print(f"[voice_bridge] GPT-4o-mini reply: {result[:80]}{'...' if len(result)>80 else ''}")
            return result
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] GPT-4o-mini error: {exc}")
            return ""

    def stream_reply_and_speak(self, prompt: str) -> str:
        """Stream GPT-4o-mini text, chunk into sentences, synthesize in background, play in order."""
        sentence_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        audio_queue: "queue.Queue[Optional[tuple[str, str]]]" = queue.Queue()
        reply_chunks: list[str] = []
        reply_lock = threading.Lock()

        def produce_sentences() -> None:
            buffer = ""
            try:
                stream = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": LLM_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=self.cfg.stream_max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    with reply_lock:
                        reply_chunks.append(delta)
                    buffer += delta
                    ready, buffer = self._extract_ready_sentences(buffer)
                    for sentence in ready:
                        sentence_queue.put(sentence)
                for sentence in self._extract_ready_sentences(buffer, final=True)[0]:
                    sentence_queue.put(sentence)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[voice_bridge] Streaming GPT-4o-mini error: {exc}")
            finally:
                sentence_queue.put(None)

        def synthesize_sentences() -> None:
            while True:
                sentence = sentence_queue.get()
                if sentence is None:
                    audio_queue.put(None)
                    return
                audio_path = self.tts_provider.synthesize_to_file(sentence)
                if audio_path:
                    audio_queue.put((sentence, str(audio_path)))

        producer = threading.Thread(target=produce_sentences, daemon=True)
        synthesizer = threading.Thread(target=synthesize_sentences, daemon=True)
        producer.start()
        synthesizer.start()

        spoken_text = ""
        while True:
            item = audio_queue.get()
            if item is None:
                break
            sentence, audio_path = item
            spoken_text = f"{spoken_text}{sentence}".strip()
            update_state("speaking", assistant_text=spoken_text)
            self._play_audio_file(audio_path)
            Path(audio_path).unlink(missing_ok=True)

        producer.join(timeout=0.5)
        synthesizer.join(timeout=0.5)
        full_reply = "".join(reply_chunks).strip()
        print(f"[voice_bridge] Streaming reply: {full_reply[:80]}{'...' if len(full_reply)>80 else ''}")
        return full_reply

    def _extract_ready_sentences(self, buffer: str, final: bool = False) -> tuple[list[str], str]:
        ready: list[str] = []
        remaining = buffer

        while remaining:
            split_idx = next((idx for idx, ch in enumerate(remaining) if ch in SENTENCE_ENDINGS), -1)
            if split_idx >= 0:
                sentence = remaining[: split_idx + 1].strip()
                remaining = remaining[split_idx + 1 :]
                if sentence:
                    ready.append(sentence)
                continue
            if len(remaining.strip()) >= STREAM_CHUNK_CHARS:
                sentence = remaining[:STREAM_CHUNK_CHARS].strip()
                remaining = remaining[STREAM_CHUNK_CHARS:]
                if sentence:
                    ready.append(sentence)
                continue
            break

        if final and remaining.strip():
            ready.append(remaining.strip())
            remaining = ""
        return ready, remaining

    def speak(self, text: str) -> None:
        text = self._prepare_reply_for_speech(text, search=False)
        print(f"[voice_bridge] Speaking: {text[:60]}{'...' if len(text)>60 else ''}")
        try:
            audio_path = self.tts_provider.synthesize_to_file(text)
            self._play_audio_file(str(audio_path))
            Path(audio_path).unlink(missing_ok=True)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] TTS error: {exc}")

    def _prepare_reply_for_speech(self, text: str, search: bool) -> str:
        cleaned = self._normalize_tts_text(text)
        if search and self.cfg.rewrite_search_reply_for_speech:
            rewritten = self._rewrite_search_reply_for_speech(cleaned)
            if rewritten:
                return self._normalize_tts_text(rewritten)
        return cleaned

    def _normalize_tts_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text

        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"!?\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"www\.\S+", "", text)
        text = re.sub(r"\[[0-9 ,;]+\]", "", text)
        text = re.sub(r"[•●◆■▶►▪◦]+", "，", text)
        text = re.sub(r"^[#>*\-\s]+", "", text, flags=re.M)
        text = text.replace("°C", "度")
        text = text.replace("°", "度")
        text = re.sub(r"(\d+(?:\.\d+)?)%", r"百分之\1", text)
        text = text.replace("%", "百分之")
        text = text.replace("&", "和")
        text = text.replace("AI", "ＡＩ")
        text = text.replace("assistant", "助理")
        text = text.replace("GPS", "ＧＰＳ")
        text = text.replace("Wi-Fi", "無線網路")
        text = text.replace("wifi", "無線網路")
        text = re.sub(r"[_*=~|]+", " ", text)
        text = re.sub(r"[()（）【】\[\]{}<>]+", " ", text)
        text = re.sub(r"\b(詳見|詳情見|來源|出處)\b[:：]?\s*$", "", text)
        text = re.sub(r"^\s*(來源|出處)\s*[:：]?\s*", "", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s*([，。！？；：,!?;:])\s*", r"\1", text)
        text = re.sub(r"([，。！？；：,!?;:]){2,}", r"\1", text)
        return text.strip(" ，。；：")

    def _rewrite_search_reply_for_speech(self, text: str) -> str:
        if not text:
            return text
        try:
            resp = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SPOKEN_REPLY_PROMPT},
                    {"role": "user", "content": text[: self.cfg.spoken_reply_max_input_chars]},
                ],
                max_tokens=self.cfg.search_reply_max_tokens,
                timeout=self.cfg.spoken_reply_timeout_sec,
            )
            rewritten = (resp.choices[0].message.content or "").strip()
            if rewritten:
                print(f"[voice_bridge] Search speech rewrite: {rewritten[:80]}{'...' if len(rewritten)>80 else ''}")
                return rewritten
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] Search speech rewrite skipped: {exc}")
        return text

    def _play_audio_file(self, file_path: str) -> None:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def update_state(phase: str, *, user_text: Optional[str] = None, assistant_text: Optional[str] = None) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STATE_PATH.exists():
        try:
            payload = json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    payload.setdefault("userText", "")
    payload.setdefault("assistantText", "")
    if user_text is not None:
        payload["userText"] = user_text
    if assistant_text is not None:
        payload["assistantText"] = assistant_text
    payload["phase"] = phase
    payload["lastUpdate"] = datetime.now(timezone.utc).astimezone().isoformat()
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def build_arg_parser(default_config_path: Path, default_input_device: Optional[int]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Zero's audio bridge")
    parser.add_argument(
        "--config",
        default=str(default_config_path),
        help=f"Path to config YAML (default: {default_config_path})",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=default_input_device,
        help="sounddevice input device index (default: config.yaml or system default)",
    )
    parser.add_argument(
        "--playback-device",
        default=DEFAULT_PLAYBACK,
        help=f"ALSA device string for local playback (default: {DEFAULT_PLAYBACK})",
    )
    parser.add_argument("--wake", default=DEFAULT_WAKE, help="Wake phrase to listen for (default: '兔兔助理')")
    return parser


def main() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        print("Please set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    pre_args, _ = pre_parser.parse_known_args()

    config_path, app_config = load_app_config(pre_args.config)
    voice_config = apply_runtime_config(app_config)
    args = build_arg_parser(config_path, voice_config.get("audio", {}).get("input_device")).parse_args()
    client = OpenAI()
    cfg = build_bridge_config(voice_config, args)
    bridge = VoiceBridge(cfg, client)
    bridge.run()


if __name__ == "__main__":
    main()
