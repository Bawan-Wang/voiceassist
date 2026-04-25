# skill.md — Available Tools & External Functions

## Services Managed by `rabbitctl.sh`

| Service | Command | Description |
|---------|---------|-------------|
| FastAPI backend | `uvicorn src.api.app:app` | Intent routing, LLM calls |
| Voice bridge | `src/bridge/voice_bridge.py` | Mic → VAD → STT → TTS pipeline |
| Bunny UI | `src/ui/assistant_ui.py` | PyGame animated face, polls `data/demo_state.json` |
| Photoframe | `run_photoframe.sh` | External Kivy photoframe app |

Usage: `./rabbitctl.sh {start|stop|restart|status}`

## Local Skills (callable via `/zero-assistant`, exec-plan 007)

Package: `src/api/skills/`

| Skill | NAME | Tokens | Action |
|-------|------|--------|--------|
| Open photoframe / album | `open_photoframe` | `相框 / 相簿 / 照片 / photoframe / album / photos` | Fade bunny → kill bunny → launch `run_photoframe.sh` (logs to `/tmp/photoframe.log`) |
| Open bunny | `open_bunny` | `兔兔 / bunny` | Signal photoframe to exit → kill photoframe → relaunch `assistant_ui.py` |

Dispatcher: `src.api.skills.match_skill(text)`. Manual `SKILLS = [...]`
list (option A) so an import error in one skill cannot disable the others.
When the local LLM tool-calling work lands, this same registry will be
exposed as the tool-call surface.

IPC: `/tmp/voiceassist_signal.json` — see `_signal.py`. Atomic writes via
`tempfile + os.replace`.

Voice bridge fast path: `src.api.skills.tokens.is_local_skill(text)` is a
pure-string helper imported eagerly so the bridge can route local commands
without touching the FastAPI stack.

### External app contract — photoframe (008)

Photoframe lives in `~/workspace/photoframe/` (separate repo, system
Python 3 + apt kivy). Contract:

| Direction | File | Writer → Reader | Purpose |
|-----------|------|-----------------|---------|
| voiceassist → photoframe | `/tmp/voiceassist_signal.json` | `open_bunny.run()` writes `photoframe_should_exit=true` | Request graceful exit |
| photoframe → voiceassist | `/tmp/photoframe.ready` | photoframe `on_start()` touches; `_graceful_exit()` removes | Health beacon |
| both directions | `/tmp/photoframe.log` | `run_photoframe.sh` redirects stdout/stderr | Postmortem on launch failure |

## External AI Tools

### OpenAI Web Search Tool (primary for search/weather, 006)
- Module: `src/api/websearch.py`
- Invoked via `client.responses.create(model="gpt-4o-mini", tools=[{"type": "web_search"}], input=...)`
- Used for: search, weather, browse intents — typical latency 3–8 s
- Disable via env: `VOICEASSIST_DISABLE_WEBSEARCH=1`
- Override model: `ZERO_WEBSEARCH_MODEL`
- Requires: `OPENAI_API_KEY` env var

### OpenClaw Agent (fallback for search/weather)
- Invoked via `subprocess.run(["openclaw", "--json", ...], timeout=90)`
- Used as fallback when OpenAI websearch fails
- Returns JSON: `{"result": {"payloads": [{"text": "..."}], "meta": {"stopReason": "..."}}}`
- 005-hardened: rejects responses with `meta.stopReason == "error"` or non-zero exit

### OpenAI GPT-4o-mini (general Q&A + final fallback)
- Invoked via `openai.OpenAI().responses.create(...)`
- Used for: general Q&A (direct from voice bridge, bypasses FastAPI)
- Also used as the final fallback in `src/api/app.py` when both websearch and OpenClaw fail
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
