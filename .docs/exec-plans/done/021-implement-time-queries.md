# 021 — Implement Time Queries

## Status: Done ✅

## Motivation

Phase 22 in [PLAN.md](../../PLAN.md) defines the next capability sequence as:

1. Time queries
2. Reminders
3. Memory

This plan implements **time queries only** as the first deterministic user-facing skill surface. It establishes stable behavior for timezone handling, phrasing, and routing before reminder scheduling depends on the same time semantics.

---

## Scope

In scope:

- Deterministic handling for time-query intents (Traditional Chinese + English variants from spec).
- Concise spoken-style replies suitable for voice output.
- Timezone behavior pinned to configured runtime timezone (`Asia/Taipei` by default).
- Tests for routing and formatting behavior.

Out of scope:

- Reminder creation, persistence, or notification delivery.
- Long-term memory storage/retrieval behavior.
- Broad NLP intent overhaul outside time-query patterns.

---

## Pre-flight

- [x] Confirm `.docs/product-specs/time-queries.md` exists and defines intended query surface.
- [x] Re-run baseline tests before changes:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [x] Confirm no active branch already implements overlapping time-query handlers.

---

## Target Behavior

For recognized time-query intents:

- The assistant answers directly with deterministic local time information.
- Reply is short and TTS-friendly (no markdown/list formatting).
- No web-search dependency for basic current-time questions.

---

## Action Items

### Step 1 — Add time-query classifier primitives

- [x] Add lightweight parser helpers in `src/api/skills/time_query.py`.
- [x] Keep classifier precedence coherent with existing shared routing policy from plan 020.

### Step 2 — Add deterministic time-query executor

- [x] Implement local deterministic formatter for time/date/weekday replies.
- [x] Keep formatting logic centralized in one module.

### Step 3 — Integrate into shared routing policy

- [x] Extend `src/api/skills/policy.py` with `RouteKind.TIME_QUERY`.
- [x] Keep backward compatibility for existing local-skill/search/chat paths.

### Step 4 — Wire API execution path

- [x] Update `src/api/app.py` to execute time-query route deterministically.
- [x] Preserve existing response envelope (`AssistResponse`) and metadata conventions.

### Step 5 — Wire voice bridge execution path

- [x] Update `src/bridge/voice_bridge.py` so recognized time queries follow deterministic path and produce spoken response.
- [x] Keep wake-word and two-step command logic unchanged.

### Step 6 — Tests

- [x] Add unit tests for parser and formatting behavior.
- [x] Add API-level tests in `tests/test_api.py` for representative time-query phrases.
- [x] Add voice-routing tests in `tests/test_voice_bridge_local_routing.py`.
- [x] Add routing-policy coverage in `tests/test_routing_policy.py`.

### Step 7 — Docs sync

- [x] Update `.docs/product-specs/intent-routing.md` to include time-query route.
- [x] Update `.docs/context.md` with implementation notes.

### Step 8 — Verification gates

- [x] Run required suite after edits to `src/api/app.py` and `src/bridge/voice_bridge.py`:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
- [x] Run full suite:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`

---

## Acceptance Criteria

- [x] Time-query intents defined by spec are recognized reliably.
- [x] Responses are deterministic, concise, and TTS-friendly.
- [x] Existing local-skill/search/chat behavior remains intact.
- [x] API and voice entrypoints both honor the same routing policy outcome.
- [x] New/updated tests pass.
- [x] Full test suite passes.

---

## Rollback Plan

If time-query changes cause regressions:

- Revert route-policy additions for time intents while keeping existing 020 routing behavior.
- Keep test cases as guardrails for re-introduction.
- Re-run full suite and restore last known-good behavior for local-skill/search/chat paths.

