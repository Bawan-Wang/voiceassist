# Time Queries in voiceassist

This page explains the deterministic time-query path added in exec-plan 021.

If you want the broader routing context, read [entrypoints.md](entrypoints.md)
and [three-routing-paths.md](three-routing-paths.md) first. This page focuses
only on the current-time / date / weekday branch.

## Why Time Queries Have Their Own Route

Time queries are intentionally not handled by general chat generation.

The repository treats them as deterministic local logic because:

- current time must come from a local clock source, not a model guess,
- reminder features already reuse the same timezone semantics, and reminder
    routing now sits ahead of time queries when reminder language is present,
- the voice path needs a short TTS-friendly answer with low latency,
- unsupported place names must ask for clarification instead of silently
  guessing a timezone.

That is why `classify_request()` returns `RouteKind.TIME_QUERY` instead of
folding these utterances into `CHAT`.

## Technologies Used

| Technology / primitive | Where | Why it is used |
|---|---|---|
| Python `datetime` | `src/api/skills/time_query.py` | Reads the current clock value locally |
| Python `zoneinfo.ZoneInfo` | `src/api/skills/time_query.py` | Converts the reply into the requested timezone |
| Curated alias table | `_ALIASES` in `src/api/skills/time_query.py` | Maps place names like `東京` / `东京` to canonical IANA timezones |
| Cheap string tokens | `_TIME_TOKENS`, `_DATE_TOKENS`, `_WEEKDAY_TOKENS` | Detects the query type without an NLP model |
| Regex cleanup | `_trim_candidate()` and `_extract_unknown_place()` | Handles ASR prefixes and place extraction |
| Dataclass contract | `TimeQueryIntent` | Carries parsed query intent from classifier to renderer |
| Shared router | `src/api/skills/policy.py` | Makes API and voice bridge agree on route selection |
| FastAPI response envelope | `src/api/app.py` | Returns deterministic reply text plus metadata |
| Voice bridge API reuse | `src/bridge/voice_bridge.py` | Lets voice runtime speak the same deterministic answer |

## End-to-End Flow

There are two runtime entrypoints, but they share the same time-query parser
and renderer once text exists.

### HTTP Text Path

```text
POST /zero-assistant
  -> AssistRequest(text)
  -> classify_request(text)
  -> parse_time_query(text)
  -> RouteKind.TIME_QUERY
  -> render_time_query_reply(intent)
  -> AssistResponse(reply_text, meta)
```

### Voice Path

```text
Microphone audio
  -> VoiceBridge._capture_utterance()
  -> VoiceBridge.transcribe()
  -> wake-word / follow-up / auto-route logic
  -> classify_request(command, raw_transcript=transcript)
  -> RouteKind.TIME_QUERY
  -> VoiceBridge._reply_via_api(command)
  -> POST /zero-assistant
  -> render_time_query_reply(intent)
  -> reply_text returned to voice bridge
  -> VoiceBridge.speak(reply_text)
```

The important architectural point is that voice does not render the clock reply
itself. It routes through the same API time-query executor so the voice and
HTTP paths share one deterministic source of truth.

## Parsing Model

The parser in `src/api/skills/time_query.py` is intentionally small and rule
based.

It does four things in order:

1. detect whether the utterance asks for time, date, or weekday,
2. resolve any known timezone alias,
3. detect whether the utterance contains an unsupported place name,
4. produce a `TimeQueryIntent` for rendering.

### Query Kinds

- `time`: `現在幾點`, `请问现在几点`, `東京時間呢`
- `date`: `今天幾號`, `今天几号`
- `weekday`: `今天星期幾`, `今天星期几`

### Alias Resolution

The parser uses a curated `_ALIASES` table rather than external geocoding.

Examples:

- `台灣` / `台湾` / `台北` -> `Asia/Taipei`
- `日本` / `東京` / `东京` -> `Asia/Tokyo`
- `紐約` / `纽约` -> `America/New_York`
- `倫敦` / `伦敦` -> `Europe/London`

### Traditional, Simplified, and ASR Variants

The parser accepts both Traditional and Simplified Chinese tokens.

It also tolerates common STT / ASR style prefixes such as:

- `請問現在幾點`
- `请问现在几点`
- `兔助理，请问现在几点`

That support is implemented with `_FILLER_PREFIXES`, `_GENERIC_PREFIXES`, and
the regex cleanup inside `_trim_candidate()`.

### Unknown Place Handling

If a place name looks intentional but is not in the alias table, the parser
does not silently fall back to `Asia/Taipei`.

Instead it returns a `TimeQueryIntent` with:

- `timezone=None`
- `needs_clarification=True`
- `label=<unknown place>`

That lets the renderer produce a clarification reply such as:

```text
抱歉，巴黎的時區我還不確定，你可以換個地名說法嗎？
```

## Rendering Model

`render_time_query_reply()` turns `TimeQueryIntent` into the final spoken reply.

The renderer:

- loads the requested timezone through `ZoneInfo`,
- calculates the local time from Python `datetime`,
- formats the period in Traditional Chinese (`凌晨`, `上午`, `中午`, `下午`, `晚上`),
- keeps the answer short for TTS,
- mentions the place name when the timezone is not the default local timezone.

Examples:

- local time -> `現在時間是晚上11點9分。`
- foreign timezone -> `日本現在時間是晚上8點整。`
- weekday -> `今天是星期六。`

## Source Code Map

| File | What it owns |
|---|---|
| `src/api/skills/time_query.py` | Intent parsing, alias resolution, clarification logic, and final reply formatting |
| `src/api/skills/policy.py` | Shared `RouteKind.TIME_QUERY` classification |
| `src/api/app.py` | HTTP execution branch and response metadata |
| `src/bridge/voice_bridge.py` | Voice-side detection of `TIME_QUERY` and API routing |
| `tests/test_time_query.py` | Parser and renderer unit coverage |
| `tests/test_api.py` | API response coverage for time queries |
| `tests/test_routing_policy.py` | Shared route classification coverage |
| `tests/test_voice_bridge_local_routing.py` | Voice bridge classification coverage |

## Key Source Snippets

### Intent contract

Path: `src/api/skills/time_query.py`

```python
@dataclass(frozen=True)
class TimeQueryIntent:
    kind: str
    timezone: str | None
    label: str
    needs_clarification: bool = False
```

This is the shared payload between parsing and rendering.

### Shared classifier branch

Path: `src/api/skills/policy.py`

```python
time_query = parse_time_query(normalized_text)
if time_query is not None:
    return RouteDecision(
        kind=RouteKind.TIME_QUERY,
        routed_text=normalized_text,
        time_query=time_query,
    )
```

This is the decision point that keeps time queries out of general chat.

### HTTP execution branch

Path: `src/api/app.py`

```python
if decision.kind is RouteKind.TIME_QUERY and decision.time_query is not None:
    from .skills.time_query import render_time_query_reply

    reply = render_time_query_reply(decision.time_query)
    return AssistResponse(
        reply_text=reply,
        meta={
            "source": "local-skill",
            "action": "time_query",
            "time_kind": decision.time_query.kind,
            "timezone": decision.time_query.timezone,
        },
    )
```

The API treats time queries as a deterministic local branch, even though the
route kind is distinct from `LOCAL_SKILL`.

### Voice bridge branch

Path: `src/bridge/voice_bridge.py`

```python
if decision.kind is RouteKind.TIME_QUERY:
    print(f"[voice_bridge] Time query detected, routing to API: {decision.routed_text}")
    update_state(self.cfg.state_path, "thinking", user_text=decision.routed_text, assistant_text="")
    reply = self._reply_via_api(decision.routed_text)
    update_state(self.cfg.state_path, "speaking", assistant_text=reply)
    self.speak(reply)
```

Voice deliberately reuses the API branch instead of inventing a second time
formatter in the bridge process.

## Verification and Guard Rails

The time-query path is covered at four levels:

- parser / renderer unit tests in `tests/test_time_query.py`
- API behavior in `tests/test_api.py`
- shared route policy in `tests/test_routing_policy.py`
- voice-side classification in `tests/test_voice_bridge_local_routing.py`

Representative guarded cases include:

- standard Traditional Chinese queries,
- Simplified Chinese variants,
- ASR-like wake-prefix forms,
- unknown place clarification,
- named timezone queries such as Tokyo and Japan.