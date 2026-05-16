# Spec: Time Queries

**Module:** `src/api/skills/`, `src/api/app.py`, `src/bridge/voice_bridge.py`
**Status:** Implemented ✅

---

## Summary

The assistant answers current time, date, weekday, and selected timezone-aware
time questions such as `現在幾點` and `日本現在幾點`.

After exec-plan 021, these queries are classified by the shared routing policy
and answered deterministically from local Python `datetime` + `zoneinfo`
without an LLM generating the clock value.

This spec is intentionally limited to answering time-related questions. It does
not cover reminder creation or persistent user memory.

---

## Goals

- Answer current local time reliably.
- Support selected named timezones and city aliases.
- Allow natural phrasing instead of only fixed keyword commands.
- Keep the final answer grounded in local code, not model-generated time text.

---

## Supported Query Types

### Local Time Queries
- `現在幾點`
- `現在時間`
- `今天幾號`
- `今天星期幾`

### Named Timezone Queries
- `日本現在幾點`
- `東京時間呢`
- `紐約現在幾點`
- `倫敦現在幾點`

### Flexible Natural Phrasing
- `兔兔助理，日本現在幾點？`
- `幫我看一下東京時間`
- `現在台灣幾點了`

---

## Expected Behaviour

### Understanding
- The system may use a structured parser to extract the intended query type and
  requested timezone or city alias.
- Parser output must be treated as interpretation only.

### Source Of Truth
- The final time answer must be calculated locally from Python datetime and
  `zoneinfo`.
- Named places must resolve through a curated alias table to canonical IANA
  timezone names.
- If a place or timezone cannot be resolved confidently, the assistant should
  ask for clarification instead of guessing.

### Reply Style
- Replies should be short and spoken-friendly.
- Replies should prefer Traditional Chinese phrasing.
- The answer should mention the requested timezone when the query is not about
  the local timezone.

---

## Initial Alias Scope

The first draft should define a small, curated alias set instead of attempting
to support all cities worldwide.

Suggested starting aliases:

| User phrase | Canonical timezone |
|-------------|--------------------|
| `台灣` / `台北` | `Asia/Taipei` |
| `日本` / `東京` | `Asia/Tokyo` |
| `紐約` | `America/New_York` |
| `倫敦` | `Europe/London` |

---

## Expected API Response

```json
{
  "reply_text": "現在日本時間是晚上八點二十分。",
  "meta": {
    "source": "local-skill",
    "action": "time_query"
  }
}
```

If clarification is required, the response should remain on the local-skill
path and return a short clarification prompt.

Example clarification response:

```json
{
  "reply_text": "抱歉，巴黎的時區我還不確定，你可以換個地名說法嗎？",
  "meta": {
    "source": "local-skill",
    "action": "time_query",
    "time_kind": "time",
    "timezone": null
  }
}
```

---

## Relationship To Other Specs

- Reminder parsing and scheduling live in `reminders.md`.
- Preference-based default timezone behavior, if added later, lives in
  `memory.md`.

---

## Implementation Notes

- The current implementation lives in `src/api/skills/time_query.py`.
- Routing is shared through `src/api/skills/policy.py` as `RouteKind.TIME_QUERY`.
- Unknown place names do not silently fall back to the local timezone; they
  return a clarification prompt on the same local-skill path.

---

## Out of Scope

- Reminder creation
- Relative-time math such as `10 分鐘後`
- Recurring schedules
- Full world-city geocoding
- Letting an LLM invent or infer the final clock time without local validation