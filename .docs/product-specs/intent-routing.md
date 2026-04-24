# Spec: Intent Routing

**Module:** `src/api/app.py`, `src/bridge/voice_bridge.py`
**Status:** Implemented ✅

---

## Summary

After a command is transcribed, the system classifies it into one of three intent categories and routes it to the appropriate handler — local execution, OpenClaw agent, or OpenAI GPT-4o-mini.

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
   └─ YES → POST /zero-assistant → OpenClaw Agent (timeout: 90s)
             │
        timeout? → speak fixed hint reply, done
        failure? → return error reply, done
        │
        ▼
3. General Q&A
   ├─ Voice bridge path → direct GPT-4o-mini streaming call
   └─ API direct path   → OpenClaw (30s) → GPT-4o-mini fallback
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

### OpenClaw Agent
- CLI invoked via `subprocess.run(["openclaw", "--json", ...], timeout=90)`
- Enabled when env var `ZERO_USE_OPENCLAW_AGENT=1` (set by `rabbitctl.sh`)
- Returns JSON: `{"payloads": [{"text": "...", "mediaUrl": null}]}`
- Search timeout reply (spoken): `"抱歉，這個問題我查比較久，你可以換個方式問我。"`
- Before querying, voice bridge speaks: `"好，我幫你查一下，請稍等。"`

### GPT-4o-mini
- Used for general Q&A from voice bridge (streaming, sentence-chunked TTS)
- Used as fallback in API path when OpenClaw fails or is disabled
- Model: `gpt-4o-mini`, max tokens: 120
- Requires: `OPENAI_API_KEY` env var

---

## API Response Contract

`POST /zero-assistant`

```json
{
  "reply_text": "...",
  "meta": {
    "source": "openclaw" | "openai" | "local"
  }
}
```

---

## Feature Flag

| Flag | Effect |
|------|--------|
| `ZERO_USE_OPENCLAW_AGENT=1` | Enable OpenClaw agent routing (default in `rabbitctl.sh`) |
| `ZERO_USE_OPENCLAW_AGENT=0` | Skip OpenClaw, go directly to GPT-4o-mini |

---

## Out of Scope

- Multi-turn conversation memory
- Intent classification via an ML model
- Routing based on user identity
