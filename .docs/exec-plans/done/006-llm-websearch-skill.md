# 006 — Replace OpenClaw with LLM + `web_search` Skill

## Status: Planned 🟡 (depends on 005 completed first)

## Motivation

OpenClaw subprocess path is slow (30–90s) and fragile (JSON shape varies, frequent
upstream 400 errors — see exec-plan 005). Replace it with OpenAI Responses API +
built-in `web_search` tool, which is:

- **Fast**: 3–8s typical
- **Streamable**: can chunk into sentences for low-latency TTS playback
- **Stable**: official tool, well-defined response schema
- **Cheaper**: no extra subprocess, no extra agent loop overhead

Keep OpenClaw as the fallback path so 005's safety net remains.

---

## Target Architecture

```
voice_bridge → POST /zero-assistant
                    │
                    ├─ intent: chitchat / qa     → GPT-4o-mini direct (existing)
                    │
                    └─ intent: search / weather  → NEW: responses.create(
                                                       model="gpt-4o-mini",
                                                       tools=[{"type": "web_search"}],
                                                       stream=True)
                                                   ↓ on failure
                                                   OpenClaw fallback (existing path from 005)
```

---

## Action Items

### Step 1 — Add new provider module

- [ ] Create `src/bridge/providers/openai_websearch.py`
  - Function `run_websearch(query: str, *, system_prompt: str | None = None) -> str`
  - Use `client.responses.create(model="gpt-4o-mini", tools=[{"type": "web_search"}], input=...)`
  - Return clean text reply
  - Raise on error (let caller decide fallback)

### Step 2 — Wire into API

- [ ] In `src/api/app.py`, add new function `_search_via_llm(query)` that calls the
      new provider
- [ ] In the search/weather branch:
  ```python
  try:
      reply_text = _search_via_llm(query)
  except Exception as e:
      print(f"[api] websearch failed: {e}, falling back to openclaw")
      reply_text = _search_via_openclaw(query)   # existing path from 005
  ```
- [ ] Keep the openclaw call (and 005 hardening) intact as fallback

### Step 3 — (Optional, stretch) Streaming TTS

- [ ] If time permits, switch `_search_via_llm` to streaming mode
- [ ] Push sentence chunks back to voice_bridge over SSE / chunked HTTP
- [ ] voice_bridge speaks each sentence as it arrives (latency ↓ further)
- [ ] If too risky for one PR, defer to a future exec-plan

### Step 4 — Tests

- [ ] Add `tests/test_websearch_provider.py`:
  - Mock `client.responses.create`, assert clean text returned
  - Mock failure, assert exception raised
- [ ] Add `tests/test_api.py` case:
  - Mock `_search_via_llm` raising → assert openclaw fallback is invoked
- [ ] `.venv/bin/pytest tests/ -v` — must stay green

### Step 5 — Config / Env

- [ ] Confirm `OPENAI_API_KEY` already in `.env`; no new key needed
- [ ] Document the new path in `.docs/specs/intent-routing.md`
- [ ] Update `.docs/context.md` with the new architecture diagram

---

## Acceptance Criteria

- [ ] "幫我查今天新北市天氣" → reply within ~5s with actual weather info
- [ ] "查一下台股今天收盤" → reply within ~5s with current info
- [ ] Manually killing the OpenAI key (or simulating timeout) → falls back to
      OpenClaw without crashing
- [ ] All pytest tests pass
- [ ] Voice bridge logs show: `[api] using websearch path` for search intents
- [ ] Commit: `feat(006): use OpenAI web_search tool for search/weather, openclaw as fallback`

---

## Rollback Plan

If 006 breaks production:

1. Set env var `VOICEASSIST_DISABLE_WEBSEARCH=1`
2. `_search_via_llm` short-circuits and raises immediately
3. Falls back to the 005-hardened OpenClaw path
4. Zero downtime

---

## Out of Scope

- Replacing the chitchat/qa GPT-4o-mini path (already fast)
- Changing wake word or VAD logic
- UI changes
