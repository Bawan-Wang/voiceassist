#!/usr/bin/env python3
"""Audio bridge that lets Zero listen + speak via OpenAI cloud APIs.

Workflow:
1. Continuously listens to the USB speakerphone microphone.
2. Uses WebRTC VAD to segment utterances.
3. Runs OpenAI Whisper (gpt-4o-transcribe) to get text.
4. Requires the wake phrase "兔兔助理" ("Bunny assistant") before acting.
5. Sends the command to an LLM (gpt-4o-mini) to craft a short reply.
6. Uses OpenAI TTS (gpt-4o-mini-tts) to speak with a female voice.
7. Continuously updates data/demo_state.json so the PyGame bunny reacts.

Set OPENAI_API_KEY in your environment before running this script.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
import difflib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Deque, Optional

import numpy as np
import onnxruntime
import sounddevice as sd
import webrtcvad
from openai import OpenAI

BASE_DIR = Path(__file__).parent.parent  # repo root (voiceassist/)
STATE_PATH = BASE_DIR / "data" / "demo_state.json"
SILERO_MODEL_PATH = BASE_DIR / "models" / "silero_vad.onnx"
SILERO_MODEL_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
DEFAULT_WAKE = "兔兔助理"
DEFAULT_PLAYBACK = "plughw:2,0"
# STT_MODEL = "gpt-4o-transcribe"
STT_MODEL = "gpt-4o-mini-transcribe"
LLM_MODEL = "gpt-4o-mini"
TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "verse"  # female-ish voice
TRIM_CHARS = " ，、。!?~'\""
SENTENCE_ENDINGS = "，,。！？!?；;：:\n"
STREAM_CHUNK_CHARS = 24


@dataclass
class BridgeConfig:
    sample_rate: int = 16_000
    frame_ms: int = 30
    padding_ms: int = 600
    input_device: Optional[int] = None
    playback_device: str = DEFAULT_PLAYBACK
    wake_variants: tuple[str, ...] = (
        "兔兔助理", "兔兔助手", "兔兔兔", "兔兔", "bunny assistant", "bunny helper", "zero",
        # 常見誤辨容錯
        "圖圖助理", "嘟嘟助理", "處處助理", "兔兔處理", "兔兔注意", "杜兔助理", "嘟兔助理", "圖兔助理",
    )
    voice: str = DEFAULT_VOICE


_SEARCH_TOKENS = (
    "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
    "網路上", "網頁", "資料", "天氣", "weather", "search", "look up", "find", "browse",
)


def is_search_intent(text: str) -> bool:
    """Return True if the command looks like a search/browse request."""
    return any(tok in text for tok in _SEARCH_TOKENS)


def ensure_silero_model() -> Optional[Path]:
    """Ensure the Silero VAD model exists locally, downloading it on first use."""
    if SILERO_MODEL_PATH.exists():
        return SILERO_MODEL_PATH

    try:
        SILERO_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = SILERO_MODEL_PATH.with_suffix(".onnx.tmp")
        print(f"[voice_bridge] Silero model missing; downloading from {SILERO_MODEL_URL}")
        urllib.request.urlretrieve(SILERO_MODEL_URL, tmp_path)
        tmp_path.replace(SILERO_MODEL_PATH)
        print(f"[voice_bridge] Silero model downloaded to {SILERO_MODEL_PATH}")
        return SILERO_MODEL_PATH
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[voice_bridge] Silero model download failed: {exc}")
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # pylint: disable=broad-except
            pass
        return None


class _SileroVADState:
    def __init__(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.audio_buffer = bytearray()
        self.voice_window: Deque[bool] = collections.deque(maxlen=5)
        self.last_is_voice = False


class VoiceBridge:
    def __init__(self, cfg: BridgeConfig, client: OpenAI) -> None:
        self.cfg = cfg
        self.client = client
        self.webrtc_vad = webrtcvad.Vad(2)
        self.frame_bytes = int(cfg.sample_rate * cfg.frame_ms / 1000) * 2  # 16-bit mono
        self.padding_frames = cfg.padding_ms // cfg.frame_ms
        self._running = True
        self._pending_wake_until: Optional[datetime] = None
        self._last_auto_command_ts = 0.0
        self._silero_session: Optional[onnxruntime.InferenceSession] = None

        silero_model_path = ensure_silero_model()
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
                    self._pending_wake_until = now + timedelta(seconds=1.2)
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
                hint = "好，我幫你查一下，請稍等。"
                print(f"[voice_bridge] Search intent detected, speaking hint first")
                update_state("thinking", user_text=command, assistant_text=hint)
                self.speak(hint)
                reply = self.generate_reply(command, search=True)
                if not reply:
                    update_state("idle", assistant_text="抱歉，沒有聽清楚。")
                    continue

                update_state("speaking", assistant_text=reply)
                self.speak(reply)
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
        if now_ts - self._last_auto_command_ts < 2.0:
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
        silero_state = _SileroVADState() if self._silero_session is not None else None

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

            if speech_prob >= 0.5:
                is_voice = True
            elif speech_prob <= 0.2:
                is_voice = False
            else:
                is_voice = silero_state.last_is_voice

            silero_state.last_is_voice = is_voice
            silero_state.voice_window.append(is_voice)
            detected_voice = silero_state.voice_window.count(True) >= 3

        return detected_voice

    def transcribe(self, audio_bytes: bytes) -> str:
        wav_bytes = self._pcm_to_wav(audio_bytes)
        buf = io.BytesIO(wav_bytes)
        buf.name = "clip.wav"
        try:
            resp = self.client.audio.transcriptions.create(
                model=STT_MODEL,
                file=buf,
                response_format="text",
            )
            text = str(resp).strip()
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
        url = "http://127.0.0.1:8000/zero-assistant"
        try:
            resp = requests.post(url, json={"text": prompt}, timeout=90)
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
                        "content": (
                            "你是兔兔助理，一個友善的繁體中文語音助理。"
                            "請用簡短的中文回答，不超過 30 個字，不使用 Markdown。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=120,
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
                            "content": (
                                "你是兔兔助理，一個友善的繁體中文語音助理。"
                                "請用簡短的中文回答，不超過 30 個字，不使用 Markdown。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=120,
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
                audio_path = self._synthesize_mp3(sentence)
                if audio_path:
                    audio_queue.put((sentence, audio_path))

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
        print(f"[voice_bridge] Speaking: {text[:60]}{'...' if len(text)>60 else ''}")
        try:
            tmp_path = self._synthesize_mp3(text)
            if not tmp_path:
                return
            self._play_audio_file(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] TTS error: {exc}")

    def _synthesize_mp3(self, text: str) -> Optional[str]:
        with self.client.audio.speech.with_streaming_response.create(
            model=TTS_MODEL,
            voice=self.cfg.voice,
            input=text,
        ) as response:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                response.stream_to_file(tmp.name)
                return tmp.name

    def _play_audio_file(self, file_path: str) -> None:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", file_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _pcm_to_wav(self, audio_bytes: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.cfg.sample_rate)
            wf.writeframes(audio_bytes)
        return buf.getvalue()


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Zero's audio bridge")
    parser.add_argument("--input-device", type=int, default=None, help="sounddevice input device index (default: system default)")
    parser.add_argument(
        "--playback-device",
        default=DEFAULT_PLAYBACK,
        help=f"ALSA device string for aplay playback (default: {DEFAULT_PLAYBACK})",
    )
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="OpenAI TTS voice name (default: verse)")
    parser.add_argument("--wake", default=DEFAULT_WAKE, help="Wake phrase to listen for (default: '兔兔助理')")
    return parser


def main() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        print("Please set OPENAI_API_KEY in your environment.")
        sys.exit(1)

    args = build_arg_parser().parse_args()
    client = OpenAI()
    cfg = BridgeConfig(
        input_device=args.input_device,
        playback_device=args.playback_device,
        voice=args.voice,
    )
    if args.wake:
        cfg.wake_variants = tuple(dict.fromkeys((args.wake, *cfg.wake_variants)))
    bridge = VoiceBridge(cfg, client)
    bridge.run()


if __name__ == "__main__":
    main()
