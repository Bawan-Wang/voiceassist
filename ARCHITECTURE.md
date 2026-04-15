# Architecture — voiceassist

## System Overview

```
[Microphone]
     │
     ▼
bridge/voice_bridge.py
  - Captures audio via sounddevice (PipeWire/pulse)
  - WebRTC VAD segments utterances
  - OpenAI Whisper STT (gpt-4o-mini-transcribe)
  - Wake word matching (3-tier: exact → token-combo → fuzzy)
  - Detects search intent → speaks "我幫你查一下" before waiting
     │
     │  POST /zero-assistant  { "text": "..." }
     ▼
api/app.py  (FastAPI, 127.0.0.1:8000)
  - Local command intents first (open photoframe, open bunny UI)
  - Search/weather/browse → openclaw agent (timeout 90s)
  - General Q&A → openclaw agent (timeout 35s)
  - Fallback → OpenAI GPT-4o-mini (if openclaw fails)
  - Returns { "reply_text": "...", "meta": { "source": "..." } }
     │
     │  writes data/demo_state.json  { phase, userText, assistantText }
     ├──────────────────────────────────────────────────────────────────►
     │                                                          ui/assistant_ui.py
     │                                                           PyGame bunny face
     │                                                           polls JSON ~60fps
     ▼
bridge/voice_bridge.py  (receives reply_text)
  - OpenAI TTS (gpt-4o-mini-tts, voice: shimmer)
  - Plays MP3 via ffplay → Speaker
```

## Component Responsibilities

| Component | File | Key Decisions |
|-----------|------|---------------|
| Voice Bridge | `bridge/voice_bridge.py` | Audio I/O, wake word, STT, TTS, search hint |
| API Backend | `api/app.py` | Intent routing, openclaw subprocess, fallback |
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
                   → openclaw agent, timeout=35s
                   → fallback: OpenAI GPT-4o-mini
```

## Data Flow for State Updates

```
voice_bridge calls update_state(phase, userText, assistantText)
    → writes data/demo_state.json
    → ui/assistant_ui.py reads it on next frame
    → face color / ear angle / mouth animation changes
```

Phases: `idle` → `listening` → `thinking` → `speaking` → `idle`
