# api.md — API Interface Definitions

## Internal REST API (`src/api/app.py`)

Base URL: `http://127.0.0.1:8000`

### `POST /zero-assistant`

Routes voice input to OpenClaw agent or OpenAI.

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
    "source": "openclaw"
  }
}
```

**Routing logic**
- Local commands (open photoframe, open bunny UI) → handled directly, no LLM call
- Search / weather / browse intent → OpenClaw agent (`timeout=90s`)
- Fallback → OpenAI GPT-4o-mini

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
