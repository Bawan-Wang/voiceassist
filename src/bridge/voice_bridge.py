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
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Optional

try:
    import sounddevice as sd
    _SOUNDDEVICE_IMPORT_ERROR: Optional[BaseException] = None
except (ImportError, OSError) as exc:
    sd = None  # type: ignore[assignment]
    _SOUNDDEVICE_IMPORT_ERROR = exc

from .runtime_config import get_selected_provider, load_app_config, resolve_project_path

if TYPE_CHECKING:
    from openai import OpenAI
    from .providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider

BASE_DIR = Path(__file__).resolve().parents[2]  # repo root (voiceassist/)
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"


@dataclass
class BridgeConfig:
    """Single source of runtime truth for the voice bridge.

    Plan 016: every field is required and populated by
    ``build_bridge_config()`` from the yaml-loaded dict. There are no
    defaults — bare ``BridgeConfig()`` raises ``TypeError`` by design.
    """

    sample_rate: int
    frame_ms: int
    padding_ms: int
    input_device: Optional[int]
    playback_device: str
    pending_wake_timeout_sec: float
    auto_route_cooldown_sec: float
    webrtc_aggressiveness: int
    silero_speech_threshold: float
    silero_silence_threshold: float
    silero_vote_window: int
    silero_vote_required: int
    search_timeout_sec: int
    direct_max_tokens: int
    stream_max_tokens: int
    search_reply_max_tokens: int
    rewrite_search_reply_for_speech: bool
    spoken_reply_timeout_sec: int
    spoken_reply_max_input_chars: int
    search_hint: str
    api_url: str
    stt_provider_type: str
    stt_provider_config: dict[str, Any]
    tts_provider_type: str
    tts_provider_config: dict[str, Any]
    wake_variants: tuple[str, ...]
    state_path: Path
    silero_model_path: Path
    silero_model_url: str
    llm_model: str
    llm_system_prompt: str
    spoken_reply_prompt: str
    trim_chars: str
    sentence_endings: str
    stream_chunk_chars: int


# Keep the lightweight helper re-export for existing tests, but route through
# the shared policy for actual execution decisions.
try:
    from src.api.skills.tokens import is_local_skill  # noqa: F401
except Exception:  # pylint: disable=broad-except
    def is_local_skill(text: str) -> bool:  # type: ignore[no-redef]
        return False

from src.api.skills.policy import RouteKind, classify_request


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
        import numpy as np

        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.audio_buffer = bytearray()
        self.voice_window: Deque[bool] = collections.deque(maxlen=vote_window)
        self.last_is_voice = False


def build_bridge_config(voice_config: dict[str, Any], args: argparse.Namespace) -> BridgeConfig:
    try:
        audio = voice_config["audio"]
        wake = voice_config["wake"]
        routing = voice_config["routing"]
        prompts = voice_config["prompts"]
        text_cfg = voice_config["text"]
        vad = voice_config["vad"]
        silero = vad["silero"]
        _, stt_provider = get_selected_provider(voice_config, "stt")
        _, tts_provider = get_selected_provider(voice_config, "tts")

        input_device = args.input_device if args.input_device is not None else audio["input_device"]
        playback_device = args.playback_device or audio["playback_device"]

        cfg = BridgeConfig(
            sample_rate=int(audio["sample_rate"]),
            frame_ms=int(audio["frame_ms"]),
            padding_ms=int(audio["padding_ms"]),
            input_device=input_device,
            playback_device=playback_device,
            pending_wake_timeout_sec=float(wake["follow_up_timeout_sec"]),
            auto_route_cooldown_sec=float(wake["auto_route_cooldown_sec"]),
            webrtc_aggressiveness=int(vad["webrtc_aggressiveness"]),
            silero_speech_threshold=float(silero["speech_threshold"]),
            silero_silence_threshold=float(silero["silence_threshold"]),
            silero_vote_window=int(silero["vote_window"]),
            silero_vote_required=int(silero["vote_required"]),
            search_timeout_sec=int(routing["search_timeout_sec"]),
            direct_max_tokens=int(routing["direct_max_tokens"]),
            stream_max_tokens=int(routing["stream_max_tokens"]),
            search_reply_max_tokens=int(routing["search_reply_max_tokens"]),
            rewrite_search_reply_for_speech=bool(routing["rewrite_search_reply_for_speech"]),
            spoken_reply_timeout_sec=int(routing["spoken_reply_timeout_sec"]),
            spoken_reply_max_input_chars=int(routing["spoken_reply_max_input_chars"]),
            search_hint=str(routing["search_hint"]),
            api_url=str(routing["api_url"]),
            stt_provider_type=str(stt_provider["type"]),
            stt_provider_config={k: v for k, v in stt_provider.items() if k not in {"type", "name"}},
            tts_provider_type=str(tts_provider["type"]),
            tts_provider_config={k: v for k, v in tts_provider.items() if k not in {"type", "name"}},
            wake_variants=tuple(wake["variants"]),
            state_path=resolve_project_path(voice_config["state_path"]),
            silero_model_path=resolve_project_path(silero["model_path"]),
            silero_model_url=str(silero["model_url"]),
            llm_model=str(routing["llm_model"]),
            llm_system_prompt=str(prompts["llm_system"]),
            spoken_reply_prompt=str(prompts["spoken_reply"]),
            trim_chars=str(text_cfg["trim_chars"]),
            sentence_endings=str(text_cfg["sentence_endings"]),
            stream_chunk_chars=int(text_cfg["stream_chunk_chars"]),
        )
    except KeyError as exc:
        raise ValueError(
            f"config.yaml missing voiceBridge key: {exc.args[0]!r}"
        ) from exc

    if args.wake:
        cfg.wake_variants = tuple(dict.fromkeys((args.wake, *cfg.wake_variants)))
    return cfg


def _require_sounddevice() -> Any:
    if sd is None:
        raise RuntimeError(
            "sounddevice is unavailable; install PortAudio and the Python sounddevice package"
        ) from _SOUNDDEVICE_IMPORT_ERROR
    return sd


class VoiceBridge:
    def __init__(self, cfg: BridgeConfig, client: OpenAI) -> None:
        import onnxruntime
        import webrtcvad

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
        self._silero_session: Optional[Any] = None

        # state flags for reminder delivery
        self._is_speaking = False
        self._bridge_phase = "idle"

        silero_model_path = ensure_silero_model(self.cfg.silero_model_path, self.cfg.silero_model_url)
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

        # start reminder poller thread
        try:
            from src.api.skills.reminder_store import list_reminders

            self._reminder_thread = threading.Thread(target=self._reminder_poller, daemon=True)
            self._reminder_thread.start()
        except Exception:
            # best-effort; poller not critical for tests
            self._reminder_thread = None

    def _update_ui_state(
        self,
        phase: str,
        *,
        user_text: Optional[str] = None,
        assistant_text: Optional[str] = None,
    ) -> None:
        self._bridge_phase = phase
        update_state(self.cfg.state_path, phase, user_text=user_text, assistant_text=assistant_text)

    def _route_reply_via_api(self, prompt: str) -> bool:
        self._update_ui_state("thinking", user_text=prompt, assistant_text="")
        reply = self._reply_via_api(prompt)
        if not reply:
            self._update_ui_state("idle", assistant_text="抱歉，沒有聽清楚。")
            return True
        self._update_ui_state("speaking", assistant_text=reply)
        self.speak(reply)
        self._update_ui_state("idle", assistant_text=reply)
        return True

    def _process_pending_follow_up(self, command: str) -> bool:
        try:
            from src.api.skills.reminders import has_pending_confirmation
        except Exception:
            return False

        if not has_pending_confirmation():
            return False

        print("[voice_bridge] Pending reminder follow-up detected, routing to API first")
        return self._route_reply_via_api(command)

    def _deliver_due_reminders_once(self) -> None:
        try:
            from src.api.skills.reminder_store import list_reminders, mark_delivered
        except Exception:
            return

        if self._bridge_phase != "idle" or getattr(self, "_is_speaking", False):
            return

        now = datetime.now(timezone.utc)
        reminders = list_reminders()
        due = [
            reminder
            for reminder in reminders
            if reminder.get("status") == "pending" and reminder.get("due_at")
        ]
        due_sorted = sorted(due, key=lambda reminder: reminder.get("due_at", ""))
        for reminder in due_sorted:
            try:
                due_dt = datetime.fromisoformat(str(reminder.get("due_at")))
            except (TypeError, ValueError):
                continue
            if due_dt > now:
                continue
            if self._bridge_phase != "idle" or getattr(self, "_is_speaking", False):
                break

            delivery_text = f"提醒你，{reminder.get('task_text') or '提醒事項'}。"
            self._update_ui_state("speaking", user_text="", assistant_text=delivery_text)
            try:
                self.speak(delivery_text)
                mark_delivered(str(reminder.get("id")))
                self._update_ui_state("idle", assistant_text=delivery_text)
            except Exception:
                self._update_ui_state("idle")
                break

    def _create_stt_provider(self) -> SherpaOnnxSpeechToTextProvider:
        from .providers import SherpaOnnxSpeechToTextProvider

        provider_type = self.cfg.stt_provider_type.lower()
        if provider_type == "sherpa_onnx_local":
            return SherpaOnnxSpeechToTextProvider(
                sample_rate=self.cfg.sample_rate,
                **self.cfg.stt_provider_config,
            )
        raise ValueError(f"Unsupported STT provider type: {self.cfg.stt_provider_type}")

    def _create_tts_provider(self) -> PiperTextToSpeechProvider:
        from .providers import PiperTextToSpeechProvider

        provider_type = self.cfg.tts_provider_type.lower()
        if provider_type == "piper_local":
            return PiperTextToSpeechProvider(**self.cfg.tts_provider_config)
        raise ValueError(f"Unsupported TTS provider type: {self.cfg.tts_provider_type}")

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)
        sounddevice = _require_sounddevice()
        sounddevice.default.samplerate = self.cfg.sample_rate
        sounddevice.default.channels = 1
        sounddevice.default.dtype = "int16"
        if self.cfg.input_device is not None:
            sounddevice.default.device = (self.cfg.input_device, None)

        print("[voice_bridge] Ready. Say '兔兔助理 ...' to wake up Zero.")
        while self._running:
            audio = self._capture_utterance()
            if not audio:
                continue

            self._update_ui_state("listening", user_text="……", assistant_text="Zero 正在傾聽中…")
            transcript = self.transcribe(audio)
            if not transcript:
                self._update_ui_state("idle")
                continue

            matched = self._match_wake_phrase(transcript)

            # Support two-step wake: say wake word first, then command shortly after.
            now = datetime.now(timezone.utc)
            if matched:
                command = transcript.split(matched, 1)[1] if matched in transcript else transcript
                command = command.lstrip(self.cfg.trim_chars).strip()
                if not command:
                    command = transcript.replace(matched, '', 1).strip()
                if not command:
                    self._pending_wake_until = now + timedelta(seconds=self.cfg.pending_wake_timeout_sec)
                    print("[voice_bridge] Wake word heard; waiting for next sentence as command")
                    self._update_ui_state("listening", user_text="請說指令", assistant_text="")
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
                        self._update_ui_state("idle")
                        continue
            print(f"[voice_bridge] Command: {command}")

            if self._process_pending_follow_up(command):
                continue

            decision = classify_request(command, raw_transcript=transcript)

            if decision.kind is RouteKind.LOCAL_SKILL:
                if decision.used_raw_transcript:
                    print("[voice_bridge] Local skill found in raw transcript (wake-word stripper ate it)")
                print(f"[voice_bridge] Local skill detected, routing to API: {decision.routed_text}")
                self._route_reply_via_api(decision.routed_text)
                continue

            if decision.kind is RouteKind.REMINDER:
                print(f"[voice_bridge] Reminder detected, routing to API: {decision.routed_text}")
                self._route_reply_via_api(decision.routed_text)
                continue

            if decision.kind is RouteKind.TIME_QUERY:
                print(f"[voice_bridge] Time query detected, routing to API: {decision.routed_text}")
                self._route_reply_via_api(decision.routed_text)
                continue

            if decision.kind is RouteKind.TOOL_NEEDED:
                hint = self.cfg.search_hint
                print(f"[voice_bridge] Search intent detected, speaking hint first")
                self._update_ui_state("thinking", user_text=decision.routed_text, assistant_text=hint)
                self.speak(hint)
                reply = self.generate_reply(decision.routed_text, search=True)
                if not reply:
                    self._update_ui_state("idle", assistant_text="抱歉，沒有聽清楚。")
                    continue

                spoken_reply = self._prepare_reply_for_speech(reply, search=True)
                self._update_ui_state("speaking", assistant_text=reply)
                self.speak(spoken_reply)
            else:
                self._update_ui_state("thinking", user_text=decision.routed_text, assistant_text="正在思考回覆…")

                reply = self.stream_reply_and_speak(decision.routed_text)
                if not reply:
                    self._update_ui_state("idle", assistant_text="抱歉，沒有聽清楚。")
                    continue

            self._update_ui_state("idle", assistant_text=reply)

    def _handle_stop(self, *_: object) -> None:
        self._running = False

    def _reminder_poller(self) -> None:
        """Background poller that delivers due reminders when bridge is idle."""
        SLEEP_SEC = 5
        while self._running:
            try:
                self._deliver_due_reminders_once()
                time.sleep(SLEEP_SEC)
            except Exception:
                time.sleep(SLEEP_SEC)

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

        sounddevice = _require_sounddevice()
        with sounddevice.RawInputStream(blocksize=self.frame_bytes // 2, device=self.cfg.input_device) as stream:
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
        import numpy as np

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
          search=True  → local /zero-assistant API (websearch path, timeout 90s)
          search=False → direct OpenAI GPT-4o-mini call
        """
        if search:
            return self._reply_via_api(prompt)
        return self._reply_via_gpt4o_mini(prompt)

    def _reply_via_api(self, prompt: str) -> str:
        """POST to local /zero-assistant (websearch path) for search/browse."""
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
                model=self.cfg.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": self.cfg.llm_system_prompt,
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
                    model=self.cfg.llm_model,
                    messages=[
                        {
                            "role": "system",
                            "content": self.cfg.llm_system_prompt,
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
            self._update_ui_state("speaking", assistant_text=spoken_text)
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
            split_idx = next((idx for idx, ch in enumerate(remaining) if ch in self.cfg.sentence_endings), -1)
            if split_idx >= 0:
                sentence = remaining[: split_idx + 1].strip()
                remaining = remaining[split_idx + 1 :]
                if sentence:
                    ready.append(sentence)
                continue
            if len(remaining.strip()) >= self.cfg.stream_chunk_chars:
                sentence = remaining[:self.cfg.stream_chunk_chars].strip()
                remaining = remaining[self.cfg.stream_chunk_chars:]
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
                model=self.cfg.llm_model,
                messages=[
                    {"role": "system", "content": self.cfg.spoken_reply_prompt},
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
        self._is_speaking = True
        try:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            self._is_speaking = False


def update_state(state_path: Path, phase: str, *, user_text: Optional[str] = None, assistant_text: Optional[str] = None) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text())
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
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def build_arg_parser(
    default_config_path: Path,
    default_input_device: Optional[int],
    *,
    default_playback: str,
    default_wake: str,
) -> argparse.ArgumentParser:
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
        default=default_playback,
        help=f"ALSA device string for local playback (default: {default_playback})",
    )
    parser.add_argument(
        "--wake",
        default=default_wake,
        help=f"Wake phrase to listen for (default: '{default_wake}')",
    )
    return parser


def main() -> None:
    from openai import OpenAI

    if "OPENAI_API_KEY" not in os.environ:
        print("Please set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    pre_args, _ = pre_parser.parse_known_args()

    config_path, app_config = load_app_config(pre_args.config)
    voice_config = app_config["voiceBridge"]
    audio_cfg = voice_config["audio"]
    wake_cfg = voice_config["wake"]
    args = build_arg_parser(
        config_path,
        audio_cfg["input_device"],
        default_playback=str(audio_cfg["playback_device"]),
        default_wake=str(wake_cfg["primary"]),
    ).parse_args()
    client = OpenAI()
    cfg = build_bridge_config(voice_config, args)
    bridge = VoiceBridge(cfg, client)
    bridge.run()


if __name__ == "__main__":
    main()
