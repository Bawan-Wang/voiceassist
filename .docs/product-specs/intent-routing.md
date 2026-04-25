# Spec: Intent Routing

**Module:** `src/api/app.py`, `src/bridge/voice_bridge.py`
**Status:** Implemented ✅

---

## Summary

After a command is transcribed, the system classifies it into one of three intent categories and routes it to the appropriate handler — local execution, OpenAI websearch / OpenClaw fallback, or plain OpenAI GPT-4o-mini.

---

## Routing Decision Tree

```
Transcribed command
        │
        ▼
1. Local command? (photoframe / bunny UI keywords)
   └─ YES → execute locally, return reply, done
        │
        ▼
2. Search intent? (see token list below)
   └─ YES → POST /zero-assistant
            ├─ try OpenAI Responses + `web_search` tool   (~3–8 s, 006)
            │     └─ success → meta.source = "openai-websearch"
            ├─ fallback to OpenClaw Agent (90 s, 005-hardened)
            │     └─ success → meta.source = "openclaw-agent"
            └─ final fallback to plain GPT-4o-mini
                  └─ meta.source = "fallback-openai"
        │
        ▼
3. General Q&A
   ├─ Voice bridge path → direct GPT-4o-mini streaming call
   └─ API direct path   → same fallback chain as search (without websearch)
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

### OpenClaw Agent (fallback)
- CLI invoked via `subprocess.run(["openclaw", "--json", ...], timeout=90)`
- Enabled when env var `ZERO_USE_OPENCLAW_AGENT=1` (set by `rabbitctl.sh`)
- Returns JSON: `{"result": {"payloads": [{"text": "..."}], "meta": {"stopReason": "..."}}}`
- 005-hardened: rejects responses with `meta.stopReason == "error"` or non-zero exit
- Search timeout reply (spoken): `"抱歉，這個問題我查比較久，請你等一下再問我一次。"`

### GPT-4o-mini (final fallback)
- Used for general Q&A from voice bridge (streaming, sentence-chunked TTS)
- Used as the last fallback in API path when both websearch and OpenClaw fail
- Model: `gpt-4o-mini`, max tokens: 120
- Requires: `OPENAI_API_KEY` env var

---

## API Response Contract

`POST /zero-assistant`

```json
{
  "reply_text": "...",
  "meta": {
    "source": "local-command" | "openai-websearch" | "openclaw-agent" | "openclaw-agent-timeout" | "fallback-openai",
    "search": true | false
  }
}
```

---

## Feature Flags

| Flag | Effect |
|------|--------|
| `VOICEASSIST_DISABLE_WEBSEARCH=1` | Skip OpenAI websearch (006), go directly to OpenClaw fallback |
| `ZERO_USE_OPENCLAW_AGENT=1` | Enable OpenClaw agent fallback (default in `rabbitctl.sh`) |
| `ZERO_USE_OPENCLAW_AGENT=0` | Skip OpenClaw fallback, go directly to GPT-4o-mini |
| `ZERO_WEBSEARCH_MODEL` | Override the websearch model (default `gpt-4o-mini`) |

---

## Out of Scope

- Multi-turn conversation memory
- Intent classification via an ML model
- Routing based on user identity
