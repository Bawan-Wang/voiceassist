# Voice Pipeline — Current Routing Logic

## Scope

This document reflects the repo's **current** split behavior, not an idealized single-router design.

There are two entry paths:

1. `bridge/voice_bridge.py` — the live microphone / STT / TTS runtime
2. `api/app.py` — the direct HTTP `/zero-assistant` endpoint

## 1) Voice Bridge Routing

Text produced by STT inside `bridge/voice_bridge.py` is routed as follows:

| Input | Route | Timeout |
|-------|-------|---------|
| Contains search tokens (`查`, `搜尋`, `找`, `天氣`, `最新`, `新聞` …) | POST `/zero-assistant` → `api/app.py` → OpenClaw Agent | 90 s |
| Everything else (General Q&A) | Direct OpenAI `gpt-4o-mini` call inside `bridge/voice_bridge.py`, streamed sentence-by-sentence to TTS | — |

## 2) Direct API Routing

Requests sent directly to `api/app.py:/zero-assistant` are routed as follows:

| Input | Route | Timeout |
|-------|-------|---------|
| `"打開相框"` / `"開啟photoframe"` | `open_photoframe()` (local) | — |
| `"打開兔兔"` / `"切回bunny"` | `open_bunny_ui()` (local) | — |
| Contains search tokens (`查`, `搜尋`, `找`, `天氣`, `最新`, `新聞` …) | OpenClaw Agent | 90 s |
| Other non-search text, with `ZERO_USE_OPENCLAW_AGENT=1` | OpenClaw Agent first | 35 s |
| Other non-search text, when agent is disabled or fails | OpenAI fallback inside `api/app.py` | — |

## Important Limitation

Because the voice bridge only forwards search-like prompts to `/zero-assistant`, local commands such as `打開相框` and `切回兔兔` are currently part of the **direct API path**, not the default bridge general-Q&A path.
