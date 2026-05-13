# api.md — API Interface Definitions

## Internal REST API (`src/api/app.py`)

Base URL: `http://127.0.0.1:8000`

### `POST /zero-assistant`

Routes already-available text to local commands, OpenAI websearch, or plain
OpenAI.

This endpoint is the HTTP text entrypoint only. It does not own microphone
capture, VAD, STT, wake-word handling, or TTS; those belong to the voice
runtime described in [technical-concepts/entrypoints.md](technical-concepts/entrypoints.md).

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
- Search / weather / browse intent → OpenAI Responses + `web_search` tool (006); on failure falls back to plain OpenAI
- Non-search → plain OpenAI Responses

**`meta.source` values**: `local-skill` | `local-command` | `openai-websearch` | `fallback-openai`

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
