# 021 — Implement Time Queries

## Status: Planned 📝

## Motivation

Phase 22 in [PLAN.md](../../PLAN.md) defines the next capability sequence as:

1. Time queries
2. Reminders
3. Memory

This plan implements **time queries only** as the first deterministic user-facing skill surface. It should establish stable behavior for timezone handling, phrasing, and routing before reminder scheduling depends on the same time semantics.

This plan assumes `.docs/product-specs/time-queries.md` has been expanded from skeleton into implementation-ready rules. If that spec is still incomplete, finish it first and then execute this plan.

---

## Scope

In scope:

- Add deterministic handling for time-query intents (Traditional Chinese + English variants already defined in spec).
- Return concise spoken-style replies suitable for voice output.
- Keep timezone behavior pinned to configured runtime timezone (`Asia/Taipei` unless overridden by future config work).
- Add tests for routing, formatting, and fallback behavior.

Out of scope:

- Reminder creation, persistence, or notification delivery.
- Long-term memory storage/retrieval behavior.
- Broad NLP intent overhaul outside time-query patterns.

---

## Pre-flight

- [ ] Confirm `.docs/product-specs/time-queries.md` is implementation-ready and explicit about:
  - supported intents/examples,
  - output style rules,
  - timezone assumptions,
  - ambiguity/error handling.
- [ ] Re-run baseline tests before changes:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [ ] Confirm no active branch already implements overlapping time-query handlers.

---

## Target Behavior

For recognized time-query intents:

- The assistant answers directly with deterministic local time information.
- Reply is short and TTS-friendly (no markdown/list formatting).
- If query is ambiguous or unsupported, return a brief clarification or fallback message as defined by spec.
- No web-search dependency for basic current-time questions.

---

## Action Items

### Step 1 — Add time-query classifier primitives

- [ ] Add/extend lightweight token/intent helpers in `src/api/skills/` (or another shared low-dependency module) per spec.
- [ ] Ensure classifier precedence remains coherent with existing shared routing policy from plan 020.

### Step 2 — Add deterministic time-query executor

- [ ] Implement a pure function for producing time-query replies from current datetime + timezone context.
- [ ] Keep formatting logic centralized (avoid duplicated phrasing between API and bridge paths).
- [ ] Follow spec-defined phrasing and 12h/24h handling.

### Step 3 — Integrate into shared routing policy

- [ ] Extend `src/api/skills/policy.py` route decision model to represent time-query handling (either as local skill category or dedicated route kind; choose one and document it).
- [ ] Keep backward compatibility for existing local-skill/search/chat paths.

### Step 4 — Wire API execution path

- [ ] Update `src/api/app.py` to execute time-query route deterministically.
- [ ] Preserve existing response envelope (`AssistResponse`) and metadata conventions.

### Step 5 — Wire voice bridge execution path

- [ ] Update `src/bridge/voice_bridge.py` so recognized time queries follow deterministic path and produce spoken response.
- [ ] Ensure wake-word and two-step command logic remain unchanged.

### Step 6 — Tests

- [ ] Add unit tests for classifier behavior and time formatting edge cases.
- [ ] Add API-level tests in `tests/test_api.py` for representative time-query phrases.
- [ ] Add voice-routing tests in `tests/test_voice_bridge_local_routing.py` (or equivalent) to verify correct route selection.
- [ ] Cover boundary cases from spec (noon/midnight, minute formatting, ambiguous phrasing fallback).

### Step 7 — Docs sync

- [ ] Update `.docs/technical-concepts/three-routing-paths.md` and/or `.docs/product-specs/intent-routing.md` to include time-query path.
- [ ] Update `.docs/context.md` with implementation notes and follow-up risks.

### Step 8 — Verification gates

- [ ] Run focused tests for touched modules first.
- [ ] Run required suite after edits to `src/api/app.py` or `src/bridge/voice_bridge.py`:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
- [ ] Run full suite:
  - `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`

---

## Acceptance Criteria

- [ ] Time-query intents defined by spec are recognized reliably.
- [ ] Responses are deterministic, concise, and TTS-friendly.
- [ ] Existing local-skill/search/chat behavior remains intact.
- [ ] API and voice entrypoints both honor the same routing policy outcome.
- [ ] New/updated tests pass, including boundary cases.
- [ ] Full test suite passes.

---

## Rollback Plan

If time-query changes cause regressions:

- Revert route-policy additions for time intents while keeping existing 020 routing behavior.
- Keep test cases (marked xfail temporarily if needed) as guardrails for re-introduction.
- Re-run full suite and restore last known-good behavior for local-skill/search/chat paths.
