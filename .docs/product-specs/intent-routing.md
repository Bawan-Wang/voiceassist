# Spec: Intent Routing

**Module:** `src/api/app.py`, `src/bridge/voice_bridge.py`
**Status:** Implemented ✅

---

## Summary

After a command is transcribed, the system classifies it into one of three intent categories and routes it to the appropriate handler — local execution, OpenAI websearch (with plain OpenAI fallback), or plain OpenAI GPT-4o-mini.

---

## Routing Decision Tree

```
Transcribed command
        │
        ▼
1. Local skill? (photoframe / bunny tokens — see `local-commands.md`)
   └─ YES → `src.api.skills.match_skill(text).run()`
            meta.source = "local-skill", meta.action = NAME
            (also short-circuited in voice_bridge via `is_local_skill()`)
        │
        ▼
2. Search intent? (see token list below)
   └─ YES → POST /zero-assistant
            ├─ try OpenAI Responses + `web_search` tool   (~3–8 s, 006)
            │     └─ success → meta.source = "openai-websearch"
            └─ fallback to plain GPT-4o-mini Responses
                  └─ meta.source = "fallback-openai"
        │
        ▼
3. General Q&A
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
- Handled entirely in `src/api/app.py` with no LLM call
- See [`local-commands.md`](local-commands.md) for full trigger and reply spec

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
    "source": "local-skill" | "local-command" | "openai-websearch" | "fallback-openai",
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
