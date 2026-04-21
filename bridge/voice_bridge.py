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
import signal
import subprocess
import sys
import tempfile
import time
import wave
import difflib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Deque, Optional

import sounddevice as sd
import webrtcvad
from openai import OpenAI

BASE_DIR = Path(__file__).parent.parent  # repo root (voiceassist/)
STATE_PATH = BASE_DIR / "data" / "demo_state.json"
DEFAULT_WAKE = "兔兔助理"
DEFAULT_PLAYBACK = "plughw:2,0"
# STT_MODEL = "gpt-4o-transcribe"
STT_MODEL = "gpt-4o-mini-transcribe"
LLM_MODEL = "gpt-4o-mini"
TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "verse"  # female-ish voice
TRIM_CHARS = " ，、。!?~'\""


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


class VoiceBridge:
    def __init__(self, cfg: BridgeConfig, client: OpenAI) -> None:
        self.cfg = cfg
        self.client = client
        self.vad = webrtcvad.Vad(2)
        self.frame_bytes = int(cfg.sample_rate * cfg.frame_ms / 1000) * 2  # 16-bit mono
        self.padding_frames = cfg.padding_ms // cfg.frame_ms
        self._running = True
        self._pending_wake_until: Optional[datetime] = None
        self._last_auto_command_ts = 0.0

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
            else:
                update_state("thinking", user_text=command, assistant_text="正在思考回覆…")

            reply = self.generate_reply(command, search=searching)
            if not reply:
                update_state("idle", assistant_text="抱歉，沒有聽清楚。")
                continue

            update_state("speaking", assistant_text=reply)
            self.speak(reply)
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

        with sd.RawInputStream(blocksize=self.frame_bytes // 2, device=self.cfg.input_device) as stream:
            while self._running:
                frame, _ = stream.read(self.frame_bytes // 2)
                if not frame:
                    continue
                pcm_bytes = bytes(frame)
                is_speech = self.vad.is_speech(pcm_bytes, self.cfg.sample_rate)

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

    def speak(self, text: str) -> None:
        print(f"[voice_bridge] Speaking: {text[:60]}{'...' if len(text)>60 else ''}")
        try:
            with self.client.audio.speech.with_streaming_response.create(
                model=TTS_MODEL,
                voice=self.cfg.voice,
                input=text,
            ) as response:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    response.stream_to_file(tmp.name)
                    tmp_path = tmp.name
            # TTS 輸出是 MP3，aplay 不支援；改用 ffplay
            # 系統有 PipeWire，不直接指定 ALSA 硬件設備，讓 PipeWire 自動路由
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] TTS error: {exc}")

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
