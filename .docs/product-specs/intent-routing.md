# Spec: Intent Routing

**Module:** `src/api/app.py`, `src/bridge/voice_bridge.py`, `src/api/skills/policy.py`
**Status:** Implemented ✅

---

## Summary

> Note (023): On 2026-05-17 exec-plan 023 tightened the LOCAL_SKILL and TIME_QUERY token matchers to reduce false positives. Bare noun mentions (e.g. "兔兔", "相框") no longer by themselves trigger a local-skill route — command-style phrasing is required. See `.docs/exec-plans/023-fix-routing-false-positives.md` and `.docs/product-specs/smoke-tests.md` for examples and regression cases.



Once text is available, the system classifies it into route categories and sends
the request to the matching handler: deterministic local execution
(including time queries), OpenAI websearch (with plain OpenAI fallback), or plain
OpenAI GPT-4o-mini.

This document starts at the text-routing stage. The voice runtime and the HTTP
endpoint still do not enter the system at the same stage, but after 020 they do
share one classifier; see
[`technical-concepts/entrypoints.md`](../technical-concepts/entrypoints.md).

---

## Routing Decision Tree

```
Transcribed command
        │
        ▼
shared `classify_request(text, raw_transcript=None)`
  │
  ├─ 1. Local skill? (photoframe / bunny tokens — see `local-commands.md`)
  │  └─ YES → `src.api.skills.match_skill(text).run()`
  │           meta.source = "local-skill", meta.action = NAME
  │           (voice bridge may use `raw_transcript` fallback for this branch)
  │
  ├─ 2. Time query? (`現在幾點` / `今天幾號` / `今天星期幾` / named timezone)
  │  └─ YES → deterministic formatter in `src/api/skills/time_query.py`
  │           meta.source = "local-skill", meta.action = "time_query"
  │
  ├─ 3. Search intent? (see token list below)
  │  └─ YES → POST /zero-assistant
  │           ├─ try OpenAI Responses + `web_search` tool   (~3–8 s, 006)
  │           │     └─ success → meta.source = "openai-websearch"
  │           └─ fallback to plain GPT-4o-mini Responses
  │                 └─ meta.source = "fallback-openai"
  │
  └─ 4. General Q&A
     ├─ Voice bridge path → direct GPT-4o-mini streaming call
     └─ API direct path   → plain GPT-4o-mini Responses (same fallback engine as search)
```

---

## Search Intent Token List

A command is classified as **search intent** if it contains any of the following tokens:

`查` `搜尋` `搜索` `找` `查詢` `查一下` `幫我查` `最新` `新聞` `網路上` `網頁` `資料` `天氣` `weather` `search` `look up` `find` `browse`

---

## Handler Behaviour

### Local Commands
- Classified centrally in `src/api/skills/policy.py`, executed in `src/api/app.py` with no LLM call
- See [`local-commands.md`](local-commands.md) for full trigger and reply spec

### Time Queries (021)
- Classified centrally in `src/api/skills/policy.py` as `RouteKind.TIME_QUERY`
- Executed deterministically by `src/api/skills/time_query.py` (no LLM call)
- API metadata: `meta.source="local-skill"`, `meta.action="time_query"`

### OpenAI Websearch (primary, 006)
- Module: `src/api/websearch.py`
- Calls `client.responses.create(model="gpt-4o-mini", tools=[{"type": "web_search"}], input=...)`
- Typical latency: 3–8 s
- Disable via env: `VOICEASSIST_DISABLE_WEBSEARCH=1`
- Before querying, voice bridge speaks: `"好，我幫你查一下，請稍等。"`

### GPT-4o-mini (websearch fallback + general Q&A)
- Used for general Q&A from voice bridge (streaming, sentence-chunked TTS)
- Used as the fallback in API path when websearch fails
- Model: `gpt-4o-mini`, max tokens: 120
- Requires: `OPENAI_API_KEY` env var

> _Historical:_ an OpenClaw subprocess (`openclaw agent --channel telegram …`)
> sat between websearch and GPT-4o-mini fallback until exec-plan 010, which
> removed it from `src/api/app.py`. The `ZERO_USE_OPENCLAW_AGENT` env var is
> no longer read.

---

## API Response Contract

`POST /zero-assistant`

```json
{
  "reply_text": "...",
  "meta": {
    "source": "local-skill" | "openai-websearch" | "fallback-openai",
    "action": "open_photoframe" | "open_bunny" | "time_query",
    "search": true | false
  }
}
```

---

## Feature Flags

| Flag | Effect |
|------|--------|
| `VOICEASSIST_DISABLE_WEBSEARCH=1` | Skip OpenAI websearch (006), go directly to the plain GPT-4o-mini fallback |
| `ZERO_WEBSEARCH_MODEL` | Override the websearch model (default `gpt-4o-mini`) |

---

## Out of Scope

- Multi-turn conversation memory
- Intent classification via an ML model
- Routing based on user identity

