# skill.md — Available Tools & External Functions

## Services Managed by `rabbitctl.sh`

| Service | Command | Description |
|---------|---------|-------------|
| FastAPI backend | `uvicorn src.api.app:app` | Intent routing, LLM calls |
| Voice bridge | `src/bridge/voice_bridge.py` | Mic → VAD → STT → TTS pipeline |
| Bunny UI | `src/ui/assistant_ui.py` | PyGame animated face, polls `data/demo_state.json` |
| Photoframe | `run_photoframe.sh` | External Kivy photoframe app |

Usage: `./rabbitctl.sh {start|stop|restart|status}`

## External AI Tools

### OpenClaw Agent
- Invoked via `subprocess.run(["openclaw", "--json", ...], timeout=90)`
- Used for: search, weather, browse intents
- Returns JSON: `{"payloads": [{"text": "...", "mediaUrl": null}]}`

### OpenAI GPT-4o-mini
- Invoked via `openai.OpenAI().responses.create(...)`
- Used for: general Q&A (direct from voice bridge, bypasses FastAPI)
- Requires: `OPENAI_API_KEY` env var

## Local AI Models

### STT — Sherpa-ONNX `sense_voice`
- Config: `config.yaml → voiceBridge.asr`
- Runs fully offline on device

### TTS — Piper
- Binary must be on `$PATH`
- Config: `config.yaml → voiceBridge.tts`
- Runs fully offline on device

### VAD — Silero (primary) / WebRTC (fallback)
- Automatic fallback if Silero model not available

## Shared State

- `data/demo_state.json` — runtime shared state between API and UI
  ```json
  { "phase": "idle|listening|thinking|speaking", "userText": "...", "assistantText": "..." }
  ```
  - Written by `src/api/app.py`
  - Read by `src/ui/assistant_ui.py`
  - Gitignored
