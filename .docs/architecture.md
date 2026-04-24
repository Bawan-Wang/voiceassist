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
  - Does not send general Q&A or local display commands to `api/app.py`
  - Search replies are normalized for TTS and may be rewritten into a speech-friendly form
  - Sentence-chunked local Piper TTS synthesis and playback via ffplay
     │
     │  POST /zero-assistant  { "text": "..." }  (search / weather only)
     ▼
api/app.py  (FastAPI, 127.0.0.1:8000)
  - Local command intents first (open photoframe, open bunny UI)
  - Search/weather/browse → openclaw agent (timeout 90s)
  - Non-search requests sent directly to this API still try OpenClaw first when enabled, then fall back to OpenAI
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
| API Backend | `api/app.py` | Direct API routing for local commands plus OpenClaw-first handling for incoming `/zero-assistant` requests |
| Bunny UI | `ui/assistant_ui.py` | Animation only, reads state from JSON |
| Control Script | `rabbitctl.sh` | Process management, env var injection |
| Shared State | `data/demo_state.json` | Bridge ↔ UI IPC (gitignored) |

## Two Runtime Entry Paths

There are currently two different routing entry paths in the repo:

- `bridge/voice_bridge.py` is the default live voice runtime.
- `api/app.py` is the direct HTTP entrypoint for `/zero-assistant`.

They do **not** make identical routing decisions today.

## Intent Routing in bridge/voice_bridge.py

```
transcribed voice input
  │
  ├─ contains search tokens
  │      → `generate_reply(..., search=True)`
  │      → POST `/zero-assistant`
  │      → receive `reply_text`
  │      → normalize / optionally rewrite / Piper playback
  │
  └─ everything else
       → `stream_reply_and_speak()`
       → direct OpenAI GPT-4o-mini streaming response
```

This means local intents defined in `api/app.py` are **not** reached by the default voice-bridge path unless the utterance is classified as search and forwarded to `/zero-assistant`.

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
                   → openclaw agent first when `ZERO_USE_OPENCLAW_AGENT=1`
                   → otherwise / on failure falls back to OpenAI inside `api/app.py`
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
- Current architecture is intentionally documented as split behavior: the voice bridge and direct API path are related, but not yet a single routing source of truth
