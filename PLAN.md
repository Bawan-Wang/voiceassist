# PLAN.md — voiceassist Global Blueprint

## Project Goal

A local voice assistant running on Raspberry Pi that:
- Listens for a wake word, transcribes speech (Sherpa-ONNX STT)
- Routes intents to a FastAPI backend or directly to OpenAI GPT-4o-mini
- Responds via local Piper TTS
- Optionally controls a photoframe UI and a bunny face display

## Current Architecture

```
src/bridge/voice_bridge.py   Mic → VAD → STT → wake word → intent routing → TTS
src/api/app.py               FastAPI backend — search/weather/browse → OpenClaw agent
src/ui/assistant_ui.py       PyGame bunny face UI
tests/                       Pytest harness
.docs/                       Specs, architecture, exec plans, rules
```

## Overall Progress

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project scaffolding & environment setup | ✅ Done |
| 2 | Voice pipeline (STT + wake word + TTS) | ✅ Done |
| 3 | FastAPI intent routing + OpenClaw agent | ✅ Done |
| 4 | Bunny UI + photoframe integration | ✅ Done |
| 5 | Project restructure (`src/`, `.docs/`) + product specs | ✅ Done |
| 6 | VLM model bridge | 🔲 Planned |
| 7 | Taiwan server racing fix | 🔲 Planned |

## Active Exec Plans

- `.docs/exec-plans/001-setup-env.md`
- `.docs/exec-plans/002-vlm-model-bridge.md`
- `.docs/exec-plans/003-taiwan-server-racing-fix.md`
