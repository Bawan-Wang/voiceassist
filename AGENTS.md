# AGENTS.md — AI Coding Agent Rules

This file defines the rules for any AI agent (GitHub Copilot, OpenClaw, etc.)
working in this repository. Read this before making any changes.

---

## Required Reading

Before answering any non-trivial request, consult these files:

- `PLAN.md` — overall roadmap and project progress
- `.docs/context.md` — current working context / where we left off
- `.docs/architecture.md` — system design
- `.docs/skill.md` — repo-specific tips and tricks
- `.docs/rules.md` — coding conventions plus currently-known repo deviations
- `.docs/tech-debt.md` — known issues (check before any refactor)
- `.docs/exec-plans/` (excluding `done/`) — active execution plans
- `.docs/product-specs/` — required reading when implementing a new feature

When an exec-plan is finished, move it from `.docs/exec-plans/` to `.docs/exec-plans/done/`.

---

## Workflow Rules

1. **Never commit or push without explicit user approval.**
   - Make changes, run tests, show results, then wait for the user to say "commit" or "push".

2. **Never restart services without explicit user approval.**
   - Do not run `rabbitctl.sh restart` unless the user says "你可以重啟" or similar.

3. **Always run tests after modifying `src/api/app.py` or `src/bridge/voice_bridge.py`.**
   - Run: `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
   - All tests must pass before reporting completion.

4. **When adding a new feature, add a corresponding test.**
   - New intent handler in `src/api/app.py` → add a test case in `tests/test_api.py`
   - New logic function → add a unit test in the appropriate test file

5. **Check `.docs/tech-debt.md` before starting any refactor.**
   - Known issues may already be documented there.

6. **Read the relevant product spec before implementing a new feature.**
   - Specs live in `.docs/product-specs/`

---

## Repository Layout

```
src/api/app.py              FastAPI backend — intent routing, LLM calls
src/bridge/voice_bridge.py  Mic → VAD → STT → wake word → route → TTS
src/ui/assistant_ui.py      PyGame bunny face UI, polls data/demo_state.json
data/demo_state.json        Runtime shared state (gitignored)
config.yaml                 Display config plus `voiceBridge` runtime/provider settings
rabbitctl.sh                Start / stop / restart / status all services
tests/                      Pytest harness (see .docs/HOW_TO_USE_THIS_REPO.md)
.docs/                      Specs, architecture, exec plans, rules, tech debt
PLAN.md                     Global blueprint and overall project progress
```

---

## LLM Routing

- **Voice bridge path**: search / weather / browse intent → local `POST /zero-assistant` in `src/api/app.py` → **OpenAI Responses API + `web_search` tool** (`src/api/websearch.py`, ~3–8 s)
- **Fallback chain on search failure**: OpenAI websearch → plain OpenAI GPT-4o-mini Responses
- **Voice bridge path**: general Q&A → direct **OpenAI GPT-4o-mini** call from `src/bridge/voice_bridge.py`
- **Direct API path**: `/zero-assistant` still handles local display commands first; same routing/fallback chain as above
- Search replies are normalized for TTS, and `src/bridge/voice_bridge.py` may rewrite noisy search text into a short spoken Traditional Chinese form before `Piper` playback
- `meta.source` values: `local-skill` | `local-command` | `openai-websearch` | `fallback-openai`
- Rollback: set `VOICEASSIST_DISABLE_WEBSEARCH=1` to skip the websearch path and go straight to the plain OpenAI fallback
- Do not assume local commands in `src/api/app.py` are reachable from the default voice-bridge path; today they are only guaranteed on the direct API path

---

## Key Constraints

- Python venv is at `.venv/` — always use `.venv/bin/python` or `.venv/bin/pytest`
- Logs: `/tmp/assistant_bridge.log`, `/tmp/bunny_ui.log`, `/tmp/voice_bridge.log`
- `data/` is gitignored — do not commit runtime state files
- The OpenClaw subprocess fallback was removed in exec-plan 010; do not reintroduce it without an explicit plan
