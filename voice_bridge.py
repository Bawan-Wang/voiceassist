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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional

import sounddevice as sd
import webrtcvad
from openai import OpenAI

BASE_DIR = Path(__file__).parent
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
    wake_variants: tuple[str, ...] = ("兔兔助理", "兔兔助手", "兔兔兔", "兔兔", "bunny assistant", "bunny helper", "zero")
    voice: str = DEFAULT_VOICE


class VoiceBridge:
    def __init__(self, cfg: BridgeConfig, client: OpenAI) -> None:
        self.cfg = cfg
        self.client = client
        self.vad = webrtcvad.Vad(2)
        self.frame_bytes = int(cfg.sample_rate * cfg.frame_ms / 1000) * 2  # 16-bit mono
        self.padding_frames = cfg.padding_ms // cfg.frame_ms
        self._running = True

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

            lower = transcript.lower()
            matched = None
            for phrase in self.cfg.wake_variants:
                if phrase in transcript or phrase.lower() in lower:
                    matched = phrase
                    break
            if not matched:
                print(f"[voice_bridge] Ignored (no wake word): {transcript}")
                update_state("idle")
                continue

            command = transcript.split(matched, 1)[1]
            command = command.lstrip(TRIM_CHARS)
            command = command.strip()
            if not command:
                command = transcript.replace(matched, '', 1).strip()
            if not command:
                print("[voice_bridge] Wake word heard but command empty")
                update_state("listening", user_text="請再說一次問題", assistant_text="")
                continue
            print(f"[voice_bridge] Command: {command}")
            update_state("thinking", user_text=command, assistant_text="正在思考回覆…")

            reply = self.generate_reply(command)
            if not reply:
                update_state("idle", assistant_text="抱歉，沒有聽清楚。")
                continue

            update_state("speaking", assistant_text=reply)
            self.speak(reply)
            update_state("idle", assistant_text=reply)

    def _handle_stop(self, *_: object) -> None:
        self._running = False

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

    def generate_reply(self, prompt: str) -> str:
        """Forward prompt to local Zero API (assistant_bridge) and return reply_text.
        Falls back to empty string on error."""
        import requests
        url = "http://127.0.0.1:8000/zero-assistant"
        try:
            resp = requests.post(url, json={"text": prompt}, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply_text", "")
            return reply.strip() if reply else ""
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[voice_bridge] Bridge LLM error: {exc}")
            return ""

    def speak(self, text: str) -> None:
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
