# voiceassist — Zero the Bunny Voice Assistant

A Raspberry Pi voice assistant with an animated bunny face UI. Speak the wake word, ask a question, and Zero replies out loud while the face animates in sync.

## Architecture

```
Microphone
    │
    ▼
bridge/voice_bridge.py   ← Silero VAD → STT (OpenAI) → wake word detection
    │
  ├─ search / weather / browse ── POST /zero-assistant
  │                                 ▼
  │                               api/app.py (FastAPI) ← OpenClaw Agent
  │
  └─ general Q&A ───────────────→ OpenAI GPT-4o-mini (direct)
    │
    │  writes data/demo_state.json
    ▼
ui/assistant_ui.py (PyGame)  ← polls JSON → animates face + text
    │
    ▼
Speaker (ffplay ← streaming TTS via OpenAI)
```

| Component | File | Role |
|---|---|---|
| Bunny UI | `ui/assistant_ui.py` | PyGame animated face, polls `data/demo_state.json` |
| Voice Bridge | `bridge/voice_bridge.py` | Mic capture, Silero VAD, STT, wake word, GPT routing, streaming TTS playback |
| API Backend | `api/app.py` | FastAPI, local intents, OpenClaw agent routing for search/weather |
| Control Script | `rabbitctl.sh` | Unified start / stop / restart / status |
| UI Config | `config.yaml` | Resolution, colors, face dimensions |
| Shared State | `data/demo_state.json` | Runtime state between bridge and UI (gitignored) |

## Prerequisites

```bash
# System dependencies
sudo apt install portaudio19-dev libportaudio2 ffmpeg

# Python virtual environment
cd /home/jh-pi/.openclaw/workspace/voiceassist
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set your OpenAI API key in `~/.bashrc`:

```bash
export OPENAI_API_KEY="sk-..."
```

On first run, `voiceassist` automatically downloads the `Silero VAD` model into
`models/`. The model file is **not** committed to git.

## Usage

```bash
# Start all services (API + UI + voice bridge)
bash rabbitctl.sh start

# Stop all services
bash rabbitctl.sh stop

# Restart
bash rabbitctl.sh restart

# Check running status
bash rabbitctl.sh status
```

Logs are written to:
- `/tmp/assistant_bridge.log` — FastAPI backend
- `/tmp/bunny_ui.log` — PyGame UI
- `/tmp/voice_bridge.log` — Voice bridge (STT, wake word, replies)

## Wake Word & Voice

The default wake word is **「兔兔助理」**. Say the wake word followed by your command in the same sentence, e.g. *「兔兔助理，今天天氣怎麼樣？」*

Override defaults via environment variables before running `rabbitctl.sh`:

| Variable | Default | Description |
|---|---|---|
| `RABBIT_WAKE` | `兔兔助理` | Wake phrase |
| `RABBIT_PLAYBACK` | `plughw:2,0` | ALSA playback device |
| `RABBIT_INPUT_DEVICE` | *(auto-detect pulse)* | sounddevice input index |

## Conversation Flow

```
idle  →  listening (wake word heard)
      →  thinking  (LLM processing)
      →  speaking  (TTS playback + mouth animation)
      →  idle
```

Each phase change updates `data/demo_state.json`, which the PyGame UI picks up within one frame (~16 ms at 60 fps).

## Supported Commands

- **Weather** — *「今天天氣」、「明天台北天氣」、「後天東京天氣」* (up to 7 days, global cities via Open-Meteo)
- **Search / browse** — *「幫我查」、「最新新聞」、「台北天氣」* routes to OpenClaw Agent via `api/app.py`
- **General Q&A** — anything else is sent directly to `GPT-4o-mini`
- **Local display commands** — *「打開相框 / 開啟photoframe」* and *「打開兔兔 / 切回bunny」* are handled locally by `api/app.py`

## Voice Pipeline

- **VAD**: `Silero VAD` (auto-downloaded on first run), fallback to `WebRTC VAD` if unavailable
- **STT**: `gpt-4o-mini-transcribe`
- **Search path**: search intent → speak quick hint → `/zero-assistant` → OpenClaw Agent
- **General Q&A path**: direct `GPT-4o-mini` streaming response
- **TTS**: sentence-chunked streaming TTS; audio is synthesized and played sentence-by-sentence via `ffplay`

## Configuration

Edit `config.yaml` to adjust display settings:

```yaml
display:
  width: 1080
  height: 1920
  fullscreen: true

assets:
  face_radius: 200
  blink_interval: 4.0
  # colors per phase: idle / listening / thinking / speaking
```
