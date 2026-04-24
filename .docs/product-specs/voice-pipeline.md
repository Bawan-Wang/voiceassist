# Spec: Voice Pipeline

**Module:** `src/bridge/voice_bridge.py`, `src/bridge/providers/`
**Status:** Implemented ✅

---

## Summary

The voice pipeline handles the full audio lifecycle: capturing microphone input, detecting speech segments, transcribing to text, and synthesizing spoken replies. All components run locally on-device.

---

## Pipeline Overview

```
[Microphone]
     │  16kHz, mono, int16, 30ms frames
     ▼
[VAD] — Voice Activity Detection
     │  segments utterances, discards silence
     ▼
[STT] — Speech-to-Text
     │  transcribed text string
     ▼
[Wake Word / Intent Logic]  ← see wake-word.md, intent-routing.md
     │  reply_text string
     ▼
[TTS] — Text-to-Speech
     │  audio chunks (sentence-chunked for streaming)
     ▼
[Playback]  ffplay → plughw:2,0
```

---

## Audio Configuration

| Parameter | Value |
|-----------|-------|
| Sample rate | 16,000 Hz |
| Channels | 1 (mono) |
| Bit depth | int16 |
| Frame duration | 30ms |
| VAD padding | 600ms |
| Playback device | `plughw:2,0` (configurable via `RABBIT_PLAYBACK`) |

---

## VAD — Voice Activity Detection

### Primary: Silero VAD
| Parameter | Value |
|-----------|-------|
| Model | `models/silero_vad.onnx` |
| Speech threshold | 0.5 |
| Silence threshold | 0.2 |
| Vote window | 5 frames |
| Required votes | 3 |

### Fallback: WebRTC VAD
- Activated automatically if Silero model is unavailable
- Aggressiveness level: 2

---

## STT — Speech-to-Text

| Parameter | Value |
|-----------|-------|
| Provider | `SherpaSenseVoice` |
| Backend | `sherpa_onnx_local` |
| Model | `sherpa-onnx-sense-voice-zh-en-ja-ko-yue` (int8 ONNX) |
| Decoding | `greedy_search` |
| Threads | 2 |
| Feature dim | 80 |
| ITN | enabled (`use_itn=true`) |

### Language Support

| Language | STT | TTS |
|----------|-----|-----|
| Mandarin Chinese (zh-CN) | ✅ | ✅ |
| English | ✅ recognized | ⚠️ TTS output is Mandarin only |
| Japanese (ja) | ✅ recognized | ❌ not supported |
| Korean (ko) | ✅ recognized | ❌ not supported |
| Cantonese (yue) | ✅ recognized | ❌ not supported |

> **Known Limitation:** STT is multilingual but TTS only supports `zh_CN`. Replies are always spoken in Mandarin regardless of input language.

---

## TTS — Text-to-Speech

| Parameter | Value |
|-----------|-------|
| Provider | `PiperHuayan` |
| Backend | `piper_local` |
| Model | `zh_CN-huayan-medium.onnx` |
| Language | Mandarin Chinese (zh-CN) only |
| Quality | medium |
| Playback | `ffplay` subprocess |

### Streaming Behaviour
- For general Q&A replies (GPT-4o-mini streaming): text is chunked into sentences
- Each sentence is synthesized and queued in a background thread
- Playback starts as soon as the first sentence is ready — does not wait for full reply

---

## Out of Scope

- Multi-language TTS output
- Cloud STT/TTS providers
- Speaker diarization
- Noise cancellation / echo suppression
