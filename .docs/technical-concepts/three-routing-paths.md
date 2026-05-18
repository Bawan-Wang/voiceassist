# Three Routing Paths in voiceassist

This document explains the three runtime paths that `voiceassist` uses after
speech is transcribed into text.

If you want to understand how requests first enter the system through the
long-lived voice runtime versus the HTTP text endpoint, read
[entrypoints.md](entrypoints.md) first. This page starts only after text is
already available.

If you want the dedicated implementation details for deterministic clock / date
/ weekday handling, read [time-queries.md](time-queries.md).

The important point is that this repository does **not** use one single
"LLM decides everything" flow.

Since exec-plan 020, these three paths are selected by the shared
`classify_request()` policy in `src/api/skills/policy.py`. The voice runtime and
HTTP endpoint still keep separate executors after that classification step.

- Deterministic local execution uses an API-backed fast path for local skills,
  reminders, and time queries.
- General conversation uses direct GPT streaming inside the voice bridge.
- Search and weather use the API path plus OpenAI `web_search`.

## Quick Comparison

| Path | Trigger | Goes through API | Uses LLM | Uses tool | Typical use |
|---|---|---:|---:|---:|---|
| Deterministic local | `RouteKind.LOCAL_SKILL`, `RouteKind.REMINDER`, or `RouteKind.TIME_QUERY` | Yes | No | No | Open photoframe, create / confirm reminder, current time / date / weekday |
| General Q&A | `RouteKind.CHAT` | No | Yes | No | Chitchat, explanation, general knowledge |
| Search / weather | `RouteKind.TOOL_NEEDED` | Yes | Yes | Yes | Real-time info, latest news, weather, browsing |

## Path 1: Deterministic Local Fast Path

### Intent

Use this path when the command is deterministic and can be handled locally.

Examples:

- `打開相框`
- `切回兔兔`
- `十分鐘後提醒我倒垃圾`
- `現在幾點`
- `今天星期幾`

### Flow

```text
User speech
  -> STT transcript
                -> classify_request(...) returns LOCAL_SKILL or REMINDER or TIME_QUERY
  -> POST /zero-assistant
      -> src/api/app.py runs match_skill(...) or execute_reminder_request(...) or render_time_query_reply(...)
  -> reply_text returned
  -> voice bridge speaks the reply
```

### Why this path exists

The repository intentionally avoids sending deterministic device actions,
reminder scheduling, and clock/date answers to GPT first. That reduces latency
and avoids the model answering *about* the command instead of executing it or
guessing local state.

### Main code paths

- `src/api/skills/tokens.py`
- `src/api/skills/reminders.py`
- `src/api/skills/reminder_store.py`
- `src/api/skills/time_query.py`
- `src/bridge/voice_bridge.py`
- `src/api/app.py`
- `src/api/skills/__init__.py`
- `src/api/skills/policy.py`

### Key snippet: pure-string local-skill detection

Path: `src/api/skills/tokens.py`

```python
def is_local_skill(text: str) -> bool:
    """Cheap pre-check used by voice_bridge to decide whether to POST
    the utterance to /zero-assistant instead of streaming via GPT."""
    return matches_photoframe(text) or matches_bunny(text)
```

This helper is intentionally lightweight so `voice_bridge.py` can import it
without pulling in the full FastAPI stack.

### Key snippet: shared route decision

Path: `src/api/skills/policy.py`

```python
decision = classify_request(command, raw_transcript=transcript)
if decision.kind is RouteKind.LOCAL_SKILL:
    self._route_reply_via_api(decision.routed_text)
elif decision.kind is RouteKind.REMINDER:
    self._route_reply_via_api(decision.routed_text)
elif decision.kind is RouteKind.TIME_QUERY:
    self._route_reply_via_api(decision.routed_text)
elif decision.kind is RouteKind.TOOL_NEEDED:
    self._route_reply_via_api(decision.routed_text)
else:
    self.stream_reply_and_speak(decision.routed_text)
```

Reminders, time queries, and local device skills all stay on the deterministic
local path, but reminder and time-query requests use dedicated route kinds so
the API can attach route-specific metadata and state handling.

### Key snippet: API dispatches to the local skill registry first

Path: `src/api/app.py`

```python
decision = classify_request(text)
if decision.kind is RouteKind.LOCAL_SKILL and decision.skill is not None:
    reply = decision.skill.run()
    return AssistResponse(
        reply_text=reply,
        meta={"source": "local-skill", "action": decision.skill.NAME},
    )
```

### Key snippet: API executes deterministic time queries locally

Path: `src/api/app.py`

```python
if decision.kind is RouteKind.REMINDER:
    outcome = execute_reminder_request(text)
    return AssistResponse(reply_text=outcome.reply_text, meta=outcome.meta)
```

Reminder requests stay on the same deterministic path as local device actions,
but the executor is the reminder parser / store instead of a skill module.

### Key snippet: API executes deterministic time queries locally

Path: `src/api/app.py`

```python
if decision.kind is RouteKind.TIME_QUERY and decision.time_query is not None:
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

For the detailed parser / renderer internals behind this branch, see
[time-queries.md](time-queries.md).

### Key snippet: manual skill registry

Path: `src/api/skills/__init__.py`

```python
from . import open_bunny, open_photoframe, tokens

SKILLS = [open_photoframe, open_bunny]

def match_skill(text: str):
    if not text:
        return None
    for skill in SKILLS:
        try:
            if skill.match(text):
                return skill
        except Exception:
            continue
    return None
```

The current repository uses a manual registry, not model-driven tool calling.

## Path 2: Direct GPT General Q&A

### Intent

Use this path for regular conversation when the utterance is not a local skill
and does not look like a search query.

Examples:

- `你好`
- `你覺得學 Python 要先學什麼`
- `幫我解釋一下 Docker 是什麼`

### Flow

```text
User speech
  -> STT transcript
    -> classify_request(...) returns CHAT
  -> voice bridge calls GPT directly
  -> reply is streamed sentence by sentence
  -> local TTS speaks the streamed reply
```

### Why this path exists

This is the lowest-friction conversational path. It avoids the extra HTTP hop to
the local API when the assistant only needs a normal language response.

### Main code paths

- `src/bridge/voice_bridge.py`

### Key snippet: branch selection in the voice bridge

Path: `src/bridge/voice_bridge.py`

```python
decision = classify_request(command, raw_transcript=transcript)
if decision.kind is RouteKind.CHAT:
    reply = self.stream_reply_and_speak(decision.routed_text)
```

When the shared classifier returns `CHAT`, the bridge goes straight to
`stream_reply_and_speak`.

### Key snippet: direct GPT streaming call

Path: `src/bridge/voice_bridge.py`

```python
stream = self.client.chat.completions.create(
    model=self.cfg.llm_model,
    messages=[
        {
            "role": "system",
            "content": self.cfg.llm_system_prompt,
        },
        {"role": "user", "content": prompt},
    ],
    max_tokens=self.cfg.stream_max_tokens,
    stream=True,
)
```

This is not a tool call. The bridge is asking the model for a direct answer and
then speaking it as the text streams back.

## Path 3: Search / Weather via API + OpenAI web_search

### Intent

Use this path for requests that need current information from the internet.

Examples:

- `幫我查台北今天的天氣`
- `最新 AI 新聞`
- `幫我找一下某家公司最近動態`

### Flow

```text
User speech
  -> STT transcript
    -> classify_request(...) returns TOOL_NEEDED
  -> POST /zero-assistant
        -> src/api/app.py sees the same tool-needed route
  -> src/api/websearch.py calls OpenAI Responses + web_search tool
  -> reply_text returned to voice bridge
  -> voice bridge normalizes speech output and speaks it
```

### Why this path exists

Real-time information should not depend on a plain LLM response without a tool.
This route uses OpenAI's built-in `web_search` so the assistant can answer with
fresh web data.

### Main code paths

- `src/bridge/voice_bridge.py`
- `src/api/app.py`
- `src/api/websearch.py`
- `src/api/skills/tokens.py`

### Key snippet: shared search/tool-needed classification

Path: `src/api/skills/policy.py`

```python
if is_search_intent(normalized_text):
    return RouteDecision(
        kind=RouteKind.TOOL_NEEDED,
        routed_text=normalized_text,
        is_search=True,
    )
```

### Key snippet: API executes the classifier decision

Path: `src/api/app.py`

```python
from .skills.policy import RouteKind, classify_request

decision = classify_request(text)

if decision.kind is RouteKind.LOCAL_SKILL and decision.skill is not None:
    reply = decision.skill.run()
    return AssistResponse(
        reply_text=reply,
        meta={"source": "local-skill", "action": decision.skill.NAME},
    )

if decision.kind is RouteKind.REMINDER:
    outcome = execute_reminder_request(text)
    return AssistResponse(reply_text=outcome.reply_text, meta=outcome.meta)

if decision.kind is RouteKind.TIME_QUERY and decision.time_query is not None:
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

if decision.kind is RouteKind.TOOL_NEEDED and os.environ.get("VOICEASSIST_DISABLE_WEBSEARCH", "").strip() != "1":
    try:
        from .websearch import run_websearch
        reply = run_websearch(decision.routed_text)
        if reply:
            return AssistResponse(
                reply_text=reply,
                meta={"source": "openai-websearch", "search": True},
            )
    except Exception as exc:
        print(f"[api] websearch failed: {exc}; falling back to openai", flush=True)
```

### Key snippet: actual OpenAI tool usage

Path: `src/api/websearch.py`

```python
resp = client.responses.create(
    model=WEBSEARCH_MODEL,
    tools=[{"type": "web_search"}],
    input=[
        {
            "role": "system",
            "content": [{"type": "input_text", "text": sys_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": query.strip()}],
        },
    ],
)
```

This is the only one of the three paths that is clearly using a tool call.

## Decision Rules Summary

If you want to add a new capability, use this checklist:

### Choose deterministic local path when

- The action is deterministic.
- The result comes from local state or the device itself.
- You do not want GPT to decide whether the action should run.
- Low latency matters.

Typical examples:

- open photoframe
- switch to bunny UI
- create or confirm a reminder
- tell current time
- tell current date
- device control

### Choose direct GPT path when

- The request is open-ended conversation.
- No external tool is required.
- A natural language answer is enough.

Typical examples:

- casual questions
- explanations
- brainstorming

### Choose search / tool path when

- The answer depends on current web data.
- Accuracy depends on external retrieval.
- You need up-to-date weather, news, or browse-like results.

Typical examples:

- current weather
- latest news
- recent company updates

## Important Architectural Note

In many agent systems, the standard pattern is:

```text
user request -> LLM decides tool call -> local runtime executes tool -> LLM writes final answer
```

That is a valid pattern, but it is **not** how this repository currently handles
local device skills.

For `voiceassist` today:

- local skills, reminders, and time queries still resolve through deterministic matching first
- the shared classifier decides local skill vs reminder vs time-query vs tool-needed vs chat
- general Q&A still goes directly to GPT from the voice bridge
- search/weather still goes through the API and uses OpenAI `web_search`

That split architecture is deliberate and should be kept in mind when adding new
features.