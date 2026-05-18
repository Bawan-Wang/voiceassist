# Voice vs HTTP Entrypoints

This page explains the two runtime entrypoints that exist in `voiceassist`
today.

If you want the answer to "what are the three routing paths after text already
exists?", see [three-routing-paths.md](three-routing-paths.md). This page
starts one stage earlier and answers a different question: how a request enters
the system in the first place.

If you want the time-query internals specifically, see
[time-queries.md](time-queries.md).

## Why There Are Two Entrypoints

The repository currently has two ways to start request handling:

- The long-lived voice runtime in `src/bridge/voice_bridge.py`
- The HTTP text endpoint `POST /zero-assistant` in `src/api/app.py`

They are related, but they do not begin from the same kind of input:

- The voice runtime starts from raw microphone audio.
- The HTTP endpoint starts from already-available text.

They still begin from different stages of the pipeline, but once text is
available they now share one request-classification function in
`src/api/skills/policy.py`.

## Voice Entrypoint

The voice entrypoint is the long-lived runtime in
`src/bridge/voice_bridge.py`, centered on `VoiceBridge.run()`.

This runtime owns everything that happens before text exists:

1. capture microphone audio,
2. segment speech with VAD,
3. transcribe audio to text,
4. decide whether the wake phrase was spoken,
5. optionally accept a short follow-up utterance as the real command,
6. optionally auto-route command-like speech without an explicit wake phrase.

### Voice Flow

```text
Microphone audio
  -> VoiceBridge._capture_utterance()
  -> VoiceBridge._frame_has_speech()
  -> VoiceBridge.transcribe()
  -> VoiceBridge._match_wake_phrase()
  -> pending wake follow-up or VoiceBridge._should_route_without_wake()
  -> voice-specific routing branch
  -> API call or direct OpenAI call
  -> local Piper TTS playback
```

### Voice-Specific Decision Points

The voice runtime has several decision points that do not exist in the HTTP
entrypoint:

- `_match_wake_phrase()` decides whether an utterance should wake the system.
- `_should_route_without_wake()` allows semi-command-like speech to run even
  without the wake phrase.
- Pending wake follow-up lets the user say only the wake phrase first, then say
  the command in the next short sentence.
- Pending reminder follow-up can bypass stateless classification and route
  straight to the API reminder resolver.
- A raw-transcript local-skill fallback protects against the wake-stripper
  accidentally eating the noun in phrases like `兔兔助理切回兔兔`.

### Voice Routing Once Text Exists

Once `VoiceBridge.run()` has text, it first checks whether a pending reminder
confirmation should consume the utterance. If not, it calls the shared
classifier:

1. `_process_pending_follow_up(command)` when reminder confirmation is active
2. `classify_request(command, raw_transcript=transcript)`
3. `RouteKind.LOCAL_SKILL` -> `_reply_via_api()`
4. `RouteKind.REMINDER` -> `_reply_via_api()`
5. `RouteKind.TIME_QUERY` -> `_reply_via_api()`
6. `RouteKind.TOOL_NEEDED` -> search hint + `_reply_via_api()`
7. `RouteKind.CHAT` -> `stream_reply_and_speak()`

That means the voice runtime can choose between two execution styles:

- `_reply_via_api()` for local-skill, reminder, time-query, and search-style requests
- `_reply_via_gpt4o_mini()` or `stream_reply_and_speak()` for direct LLM chat

For normal conversation, the voice runtime bypasses the local HTTP API and
talks to OpenAI directly. That is why voice chat can stream sentence chunks to
local TTS without waiting for the API layer.

### Voice Local Skill Example

```text
"兔兔助理切回兔兔"
  -> wake word matched
  -> command extracted
  -> command may become "切回" after wake stripping
  -> raw transcript still contains "兔兔"
  -> local-skill fallback catches it
  -> _reply_via_api("兔兔助理切回兔兔")
  -> POST /zero-assistant
  -> src/api/app.py runs open_bunny skill
  -> reply spoken locally by src/bridge/voice_bridge.py
```

### Voice Search Example

```text
"兔兔助理幫我查新北天氣"
  -> wake word matched
  -> command = "幫我查新北天氣"
  -> classify_request(...) returns TOOL_NEEDED
  -> speak search hint
  -> _reply_via_api(command)
  -> POST /zero-assistant
  -> src/api/app.py calls run_websearch()
  -> reply_text returned to src/bridge/voice_bridge.py
  -> normalize for speech
  -> optional spoken rewrite
  -> Piper playback
```

### Voice Chat Example

```text
"兔兔助理你覺得 Docker 是什麼"
  -> wake word matched
  -> command extracted
  -> classify_request(...) returns CHAT
  -> stream_reply_and_speak(command)
  -> direct GPT streaming response
  -> local TTS plays sentence chunks as they become ready
```

## HTTP Entrypoint

The HTTP entrypoint is `POST /zero-assistant` in `src/api/app.py`.

It receives text that already exists. Because of that, it does not own:

- microphone capture,
- VAD,
- STT,
- wake-word handling,
- pending wake follow-up,
- auto-route without wake,
- local audio playback or TTS.

### HTTP Flow

```text
HTTP POST /zero-assistant
  -> AssistRequest(text=...)
  -> pending reminder follow-up or classify_request(text)
  -> local skill or deterministic reminder or deterministic time query or run_websearch() or plain OpenAI fallback
  -> JSON response
```

### HTTP Routing Order

The HTTP endpoint now routes in this order:

1. `handle_pending_follow_up(text)` when a reminder confirmation is active
2. `match_skill(text)`
3. `parse_reminder(text)`
4. `parse_time_query(text)`
5. `is_search_intent(text)`
6. plain OpenAI fallback

That means the HTTP layer is the canonical execution owner for deterministic
local skills, but it is not the only entrypoint in the repo.

### HTTP Response Contract

`POST /zero-assistant` returns:

```json
{
  "reply_text": "...",
  "meta": {
    "source": "local-skill | openai-websearch | fallback-openai",
    "action": "optional skill name | create_reminder | confirm_reminder | cancel_reminder | time_query",
    "search": true
  }
}
```

Time-query replies also use this JSON envelope and add `meta.action =
"time_query"` plus `time_kind` and `timezone` fields. Reminder replies stay
on `meta.source = "local-skill"` and may add reminder-specific fields such as
`reminder_id`, `reminder_status`, or pending-confirmation details.

For a direct HTTP caller, that JSON response is the final output. Unlike the
voice runtime, the HTTP entrypoint does not speak the answer.

### Direct HTTP Chat Example

```text
POST /zero-assistant {"text": "你好"}
  -> no local skill match
  -> no reminder match
  -> no time query match
  -> no search intent
  -> plain OpenAI fallback
  -> returns JSON only
```

## Shared Helpers and Ownership

The repo now shares a routing policy module between the two entrypoints.

| Module | What It Owns | What It Does Not Own |
|---|---|---|
| `src/api/skills/policy.py` | Shared `classify_request()` policy and `RouteDecision` / `RouteKind` | Wake-word handling, HTTP response formatting, TTS, direct GPT execution |
| `src/api/skills/tokens.py` | Cheap string helpers such as `is_local_skill()` and `is_search_intent()` | Wake-word logic, HTTP request handling, direct GPT chat execution |
| `src/api/skills/__init__.py` | Local skill registry and `match_skill()` dispatcher | Audio pipeline, shared end-to-end routing policy, general chat |
| `src/api/skills/reminders.py` + `reminder_store.py` | Deterministic reminder parsing, pending confirmation, and durable reminder storage | Wake-word handling, TTS, direct GPT chat execution |
| `src/api/websearch.py` | OpenAI Responses `web_search` tool call | Wake-word handling, TTS, direct voice chat streaming |

Two details matter here:

- `src/bridge/voice_bridge.py` and `src/api/app.py` both call `classify_request()`.
- The voice runtime still reaches local-skill execution, reminder handling,
  time-query rendering, and `run_websearch()` indirectly by posting text to
  `POST /zero-assistant` for non-chat requests.

So the repository now shares one classifier, while still keeping separate
executors on the voice and HTTP sides.

## Current Differences

The two entrypoints still differ in important ways even after 020:

| Topic | Voice Runtime | HTTP Endpoint |
|---|---|---|
| Trigger source | Microphone audio | HTTP text request |
| Input type | Raw audio, then transcript | Text only |
| Wake-word handling | Yes | No |
| Pending follow-up after wake | Yes | No |
| Auto-route without wake | Yes | No |
| Raw-transcript local-skill fallback | Yes, via `classify_request(..., raw_transcript=...)` | No |
| Direct LLM usage | Yes, for normal chat | Yes, as non-search fallback |
| Uses local HTTP API | Sometimes | It is the HTTP API |
| TTS ownership | Yes | No |
| Response shape | Spoken audio plus state updates | JSON payload |

The most important architectural difference is this:

- Voice can bypass the API for general chat.
- HTTP never owns the voice-specific pre-text stages.

That is why questions like "does HTTP own all LLM traffic?" do not have a
simple yes/no answer in the current architecture.

## Relationship to Three Routing Paths

The page [three-routing-paths.md](three-routing-paths.md) describes what
happens after text is already available.

This page describes what happens before that point and where the request first
enters the system.

## Current Note

This document reflects the architecture after the shared-routing, time-query,
reminder, and false-positive fixes. The repo shares request classification,
but the voice runtime and HTTP endpoint still start from different stages and
keep separate executors.