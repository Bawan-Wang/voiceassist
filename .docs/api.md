# api.md — API Interface Definitions

## Internal REST API (`src/api/app.py`)

Base URL: `http://127.0.0.1:8000`

### `POST /zero-assistant`

Routes voice input to local commands, OpenAI websearch, OpenClaw, or plain OpenAI.

**Request**
```json
{
  "text": "幫我查台北天氣"
}
```

**Response**
```json
{
  "reply_text": "台北今天晴天，28°C。",
  "meta": {
    "source": "openai-websearch",
    "search": true
  }
}
```

**Routing logic** (see `.docs/product-specs/intent-routing.md` for full tree)
- Local commands (open photoframe, open bunny UI) → handled directly, no LLM call
- Search / weather / browse intent → OpenAI Responses + `web_search` tool (006); on failure falls back to OpenClaw (005-hardened); final fallback to plain OpenAI
- Non-search → OpenClaw → OpenAI fallback

**`meta.source` values**: `local-command` | `openai-websearch` | `openclaw-agent` | `openclaw-agent-timeout` | `fallback-openai`

---

### `GET /health`

Returns `{"status": "ok"}` — used by `rabbitctl.sh status`.

---

## Voice Bridge Internal Flow (`src/bridge/voice_bridge.py`)

Not an HTTP API — internal function call chain:

```
capture_audio() → vad_segment() → stt_transcribe()
  → is_wake_word() → is_search_intent()
    → POST /zero-assistant  (search path)
    → openai_respond()      (general Q&A path)
  → tts_speak()
```
