# AGENTS.md — AI Coding Agent Rules

This file defines the rules for any AI agent (GitHub Copilot, OpenClaw, etc.)
working in this repository. Read this before making any changes.

---

## Workflow Rules

1. **Never commit or push without explicit user approval.**
   - Make changes, run tests, show results, then wait for the user to say "commit" or "push".

2. **Never restart services without explicit user approval.**
   - Do not run `rabbitctl.sh restart` unless the user says "你可以重啟" or similar.

3. **Always run tests after modifying `api/app.py` or `bridge/voice_bridge.py`.**
   - Run: `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
   - All tests must pass before reporting completion.

4. **When adding a new feature, add a corresponding test.**
   - New intent handler in `api/app.py` → add a test case in `tests/test_api.py`
   - New logic function → add a unit test in the appropriate test file

5. **Check `docs/tech-debt.md` before starting any refactor.**
   - Known issues may already be documented there.

6. **Read the relevant product spec before implementing a new feature.**
   - Specs live in `docs/product-specs/`

---

## Repository Layout

```
api/app.py              FastAPI backend — intent routing, LLM calls
bridge/voice_bridge.py  Mic → VAD → STT → wake word → route → TTS
ui/assistant_ui.py      PyGame bunny face UI, polls data/demo_state.json
data/demo_state.json    Runtime shared state (gitignored)
config.yaml             Display/face config for the UI
rabbitctl.sh            Start / stop / restart / status all services
tests/                  Pytest harness (see docs/HOW_TO_USE_THIS_REPO.md)
docs/                   Specs, architecture, tech debt
```

---

## LLM Routing

- Search / weather / browse intent → local `POST /zero-assistant` in `api/app.py` → OpenClaw Agent (`timeout=90s`)
- General Q&A → direct **OpenAI GPT-4o-mini** call from `bridge/voice_bridge.py`
- Search replies are normalized for TTS, and `bridge/voice_bridge.py` may rewrite noisy search text into a short spoken Traditional Chinese form before `Piper` playback
- Do not assume `api/app.py` handles general Q&A for the voice bridge unless the code has been changed again

---

## Key Constraints

- Python venv is at `.venv/` — always use `.venv/bin/python` or `.venv/bin/pytest`
- Logs: `/tmp/assistant_bridge.log`, `/tmp/bunny_ui.log`, `/tmp/voice_bridge.log`
- `data/` is gitignored — do not commit runtime state files
- openclaw stderr must NOT be merged with stdout (it pollutes JSON output)
