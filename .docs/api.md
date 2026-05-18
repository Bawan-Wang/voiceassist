# api.md — API Interface Definitions

## Internal REST API (`src/api/app.py`)

Base URL: `http://127.0.0.1:8000`

### `POST /zero-assistant`

Routes already-available text through the shared classifier to a local skill,
deterministic reminder flow, deterministic time query, OpenAI websearch, or
plain OpenAI.

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
- Pending reminder follow-up is resolved first when a reminder confirmation is active
- Shared classifier (`src/api/skills/policy.py`) returns `LOCAL_SKILL`, `REMINDER`, `TIME_QUERY`, `TOOL_NEEDED`, or `CHAT`
- `LOCAL_SKILL` (open photoframe, open bunny UI) → handled directly, no LLM call
- `REMINDER` → deterministic parser / store flow in `src/api/skills/reminders.py`
- `TIME_QUERY` → deterministic formatter in `src/api/skills/time_query.py`
- `TOOL_NEEDED` (search / weather / browse) → OpenAI Responses + `web_search` tool (006); on failure falls back to plain OpenAI
- `CHAT` → plain OpenAI Responses

**`meta.source` values**: `local-skill` | `openai-websearch` | `fallback-openai`

---

There is currently no dedicated `GET /health` endpoint. `rabbitctl.sh status`
checks process state with `pgrep` rather than calling the API.

---

## Voice Bridge Internal Flow (`src/bridge/voice_bridge.py`)

Not an HTTP API — conceptual runtime flow:

```
capture_audio() → vad_segment() → stt_transcribe()
  → wake-word / follow-up gating
  → pending reminder follow-up or classify_request(command, raw_transcript=transcript)
    → LOCAL_SKILL → POST /zero-assistant → skill.run()
    → REMINDER → POST /zero-assistant → execute_reminder_request()
    → TIME_QUERY → POST /zero-assistant → render_time_query_reply()
    → TOOL_NEEDED → POST /zero-assistant → run_websearch() or plain OpenAI fallback
    → CHAT → direct OpenAI streaming in bridge
  → tts_speak()
```
