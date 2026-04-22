# Architecture — voiceassist

## System Overview

```
[Microphone]
     │
     ▼
bridge/voice_bridge.py
  - Captures audio via sounddevice (PipeWire/pulse)
  - Silero VAD segments utterances (falls back to WebRTC VAD)
  - Local Sherpa-ONNX STT (sense_voice)
  - Wake word matching (3-tier: exact → token-combo → fuzzy)
  - Detects search intent → speaks "我幫你查一下" before waiting
  - General Q&A → direct GPT-4o-mini streaming response
  - Search replies are normalized for TTS and may be rewritten into a speech-friendly form
  - Sentence-chunked local Piper TTS synthesis and playback via ffplay
     │
     │  POST /zero-assistant  { "text": "..." }  (search / weather only)
     ▼
api/app.py  (FastAPI, 127.0.0.1:8000)
  - Local command intents first (open photoframe, open bunny UI)
  - Search/weather/browse → openclaw agent (timeout 90s)
  - General Q&A is no longer routed here by the voice bridge
  - Returns { "reply_text": "...", "meta": { "source": "..." } }
     │
     │  writes data/demo_state.json  { phase, userText, assistantText }
     ├──────────────────────────────────────────────────────────────────►
     │                                                          ui/assistant_ui.py
     │                                                           PyGame bunny face
     │                                                           polls JSON ~60fps
     ▼
bridge/voice_bridge.py  (receives reply_text)
  - Search path: normalize text → optional GPT spoken rewrite → local Piper TTS
  - General Q&A path: sentence-chunked local Piper TTS
  - Plays WAV via ffplay → Speaker
```

## Component Responsibilities

| Component | File | Key Decisions |
|-----------|------|---------------|
| Voice Bridge | `bridge/voice_bridge.py` | Audio I/O, Silero/WebRTC VAD, wake word, STT, GPT direct path, search speech cleanup, streaming TTS |
| API Backend | `api/app.py` | Intent routing and OpenClaw subprocess for search/weather/local commands |
| Bunny UI | `ui/assistant_ui.py` | Animation only, reads state from JSON |
| Control Script | `rabbitctl.sh` | Process management, env var injection |
| Shared State | `data/demo_state.json` | Bridge ↔ UI IPC (gitignored) |

## Intent Routing in api/app.py

```
text input
    │
    ├─ "打開相框" / "開啟photoframe"  → local: open_photoframe()
    ├─ "打開兔兔" / "切回bunny"       → local: open_bunny_ui()
    │
    └─ everything else
           │
           ├─ contains search tokens (查/搜尋/找/天氣/最新/新聞…)
           │       → openclaw agent, timeout=90s
           │
           └─ general Q&A
               → OpenAI GPT-4o-mini (direct from `voice_bridge.py`)
```

Search replies then stay inside `bridge/voice_bridge.py` for a second stage:

```
reply_text from /zero-assistant
    → `_normalize_tts_text()` removes URLs, markdown, citations, and symbol noise
    → `_rewrite_search_reply_for_speech()` asks `GPT-4o-mini` for a short spoken zh-TW version
    → `PiperTextToSpeechProvider`
```

## Data Flow for State Updates

```
voice_bridge calls update_state(phase, userText, assistantText)
    → writes data/demo_state.json
    → ui/assistant_ui.py reads it on next frame
    → face color / ear angle / mouth animation changes
```

Phases: `idle` → `listening` → `thinking` → `speaking` → `idle`

## Runtime Notes

- `Silero VAD`, `Sherpa-ONNX`, and `Piper` model files are downloaded automatically on first run to `models/`
- `models/` is intentionally gitignored; runtime assets stay local
- General Q&A playback starts sentence-by-sentence rather than waiting for the full reply
- Search playback adds a cleanup step before `Piper` so OpenClaw-style search results sound more natural when spoken
