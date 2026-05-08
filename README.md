# voiceassist — Zero the Bunny Voice Assistant

A Raspberry Pi voice assistant with an animated bunny face UI. Speak the wake word, ask a question, and Zero replies out loud while the face animates in sync.

## Architecture

```
Microphone
  │
  ▼
bridge/voice_bridge.py   ← Silero VAD → STT (Sherpa-ONNX local) → wake word detection
  │
  ├─ search / weather / browse ── POST /zero-assistant
  │                                 ▼
  │                               api/app.py (FastAPI) → OpenClaw Agent
  │                                 ▼
  │                               reply_text back to bridge
  │                                 ▼
  │                               normalize spoken text → optional spoken rewrite → Piper
  │
  └─ general Q&A ───────────────→ OpenAI GPT-4o-mini (direct, streaming in bridge)
  │
  │  writes data/demo_state.json
  ▼
ui/assistant_ui.py (PyGame)  ← polls JSON → animates face + text
  │
  ▼
Speaker (ffplay ← local Piper playback)
```

| Component | File | Role |
|---|---|---|
| Bunny UI | `ui/assistant_ui.py` | PyGame animated face, polls `data/demo_state.json` |
| Voice Bridge | `bridge/voice_bridge.py` | Mic capture, Silero VAD, STT, wake word, GPT routing, search-reply speech cleanup, streaming TTS playback |
| API Backend | `api/app.py` | FastAPI entrypoint for local intents plus OpenClaw/OpenAI routing when `/zero-assistant` is called directly |
| Control Script | `rabbitctl.sh` | Unified start / stop / restart / status |
| UI + Voice Config | `config.yaml` | UI settings plus `voiceBridge` runtime config for VAD/STT/TTS/routing/model selection |
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

# For local tests / CI tooling
python -m pip install -r requirements-dev.txt
```

Set your OpenAI API key in `~/.bashrc`:

```bash
export OPENAI_API_KEY="sk-..."
```

On first run, `voiceassist` automatically downloads local model assets into
`models/` (`Silero VAD`, `Sherpa-ONNX`, and `Piper`). These files are **not**
committed to git.

## Hosted CI

GitHub Actions now provides the portable CI baseline under `.github/workflows/`:

- `CI` runs on `ubuntu-latest`, installs `requirements.txt` plus `requirements-dev.txt`, runs `pytest -q`, then runs `pip-audit` and `gitleaks` as informational scans while the initial signal is being tuned.
- `CodeQL` runs GitHub-hosted Python static analysis for pull requests and pushes to `main`.
- `Hardware Smoke` is a manual `workflow_dispatch` job on the dedicated self-hosted Pi runner (`self-hosted`, `linux`, `ARM64`, `voiceassist-pi`). It runs against `/home/jh-pi/.openclaw/workspace/voiceassist`, validates config load plus `rabbitctl.sh` start / status / stop, serializes runs with concurrency, and uploads `/tmp` logs on failure.

`CI` and `CodeQL` are the intended pull-request baseline once stabilized on the default branch. `Hardware Smoke` is intentionally manual and non-blocking so the dedicated Pi device remains under explicit operator control.

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

- **Voice bridge: weather / search / browse** — *「幫我查」、「最新新聞」、「台北天氣」* routes to `api/app.py`, which then calls the OpenClaw Agent
- **Voice bridge: general Q&A** — anything not classified as search is answered directly by `bridge/voice_bridge.py` via `GPT-4o-mini`
- **Direct API: local display commands** — *「打開相框 / 開啟photoframe」* and *「打開兔兔 / 切回bunny」* are handled inside `api/app.py`
- **Current limitation** — because the voice bridge only sends search-like prompts to `/zero-assistant`, those local display commands are currently available through the API path, but not through the default voice-bridge general-Q&A path

## Voice Pipeline

- **VAD**: `Silero VAD` (auto-downloaded on first run), fallback to `WebRTC VAD` if unavailable
- **STT**: local `Sherpa-ONNX` (`sense_voice` int8 model, auto-downloaded on first run)
- **Voice-bridge search path**: search intent → speak quick hint → `/zero-assistant` → OpenClaw Agent in `api/app.py` → local TTS text normalization → spoken-form rewrite for noisy results → `Piper`
- **Voice-bridge general Q&A path**: direct `GPT-4o-mini` streaming response inside `bridge/voice_bridge.py`
- **Direct API path**: requests sent straight to `/zero-assistant` still hit local command handlers first, then use OpenClaw-first routing when `ZERO_USE_OPENCLAW_AGENT=1`, with OpenAI fallback inside `api/app.py`
- **TTS**: local `Piper TTS`; search replies are normalized before playback and may be rewritten into a more spoken-friendly Traditional Chinese form before synthesis, while general Q&A is played sentence-by-sentence from the streaming GPT output

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

voiceBridge:
  stt:
    active: "SherpaSenseVoice"
  tts:
    active: "PiperHuayan"
```

`config.yaml` now also controls the voice pipeline. The `voiceBridge` section lets you:

- choose the active STT / TTS provider entry via `stt.active` and `tts.active`
- change model paths and download URLs per provider
- tune VAD thresholds, wake behavior, routing timeouts, and prompts
- keep `rabbitctl.sh`, `bridge/voice_bridge.py`, and the UI pointed at the same config file

If you later add another provider entry, you can switch models by editing only `config.yaml`.
```
