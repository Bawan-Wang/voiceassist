# 023 — Fix Routing False Positives

## Status: Done ✅

## Motivation

The current shared routing layer had two confirmed false-positive classes:

1. ordinary chat that mentions `兔兔`, `bunny`, `相框`, or `照片` could be
   misrouted into `LOCAL_SKILL`
2. conversational phrases such as `我有時間嗎` / `請問有時間嗎` could be
   misrouted into `TIME_QUERY`

These were boundary-correctness bugs in the classifier that sits in front of
both the HTTP and voice execution paths.

This plan fixed those false positives before reminder routing adds another
branch to the same decision layer.

---

## Scope

In scope:

- tighten local-skill matching so noun mention alone does not trigger device UI
  actions
- tighten time-query parsing so everyday `有時間嗎`-style conversation does not
  become a clock/timezone clarification flow
- add regression coverage for the reproduced false-positive cases
- update routing docs where the matcher rules changed the documented intent
  boundary

Out of scope:

- reminder creation or reminder route integration
- broad NLP redesign or model-based intent classification
- wake-word behavior changes
- changes to photoframe / bunny process management behavior

---

## Reproduced Problems

Confirmed false positives were:

- `你喜歡兔兔嗎` -> incorrectly routed to `open_bunny`
- `兔兔好可愛` -> incorrectly routed to `open_bunny`
- `相框是什麼` -> incorrectly routed to `open_photoframe`
- `我想看照片展` -> incorrectly routed to `open_photoframe`
- `我有時間嗎` -> incorrectly routed to `TIME_QUERY`
- `請問有時間嗎` -> incorrectly routed to `TIME_QUERY`

---

## Pre-flight

- [x] Snapshot the baseline suite:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [x] Re-read the current routing boundary in:
  - [src/api/skills/tokens.py](../../src/api/skills/tokens.py)
  - [src/api/skills/time_query.py](../../src/api/skills/time_query.py)
  - [src/api/skills/policy.py](../../src/api/skills/policy.py)
- [x] Preserve the existing architectural rule that local skill still outranks
      time query, search, and chat when the command is actually a device action

---

## Target Behavior

After this plan landed:

- ordinary chat that merely mentions bunny/photoframe nouns stays on the
  `CHAT` path
- actual photoframe / bunny commands still route reliably to `LOCAL_SKILL`
- conversational `有時間嗎`-style phrasing stays on the `CHAT` path
- genuine time/date/weekday questions still route reliably to `TIME_QUERY`
- API and voice entrypoints continue to agree because the fix stays in the
  shared classifier/helpers

---

## Action Items

### Step 1 — Tighten local-skill token rules

- [x] Rework `matches_bunny()` and `matches_photoframe()` in
      `src/api/skills/tokens.py` so bare noun mention is no longer sufficient
      for command intent
- [x] Keep support for existing command phrasing such as:
  - `切回兔兔`
  - `打開兔兔`
  - `打開相框`
  - `打開相簿`
  - `打開照片`
- [x] Make the command boundary explicit and testable instead of relying on
      extremely broad substring heuristics

### Step 2 — Tighten time-query parsing

- [x] Refine `src/api/skills/time_query.py` so generic conversational
      `有時間嗎 / 有时间吗` phrasing is not treated as a clock query
- [x] Preserve the current supported time-query surface for:
  - current time
  - date
  - weekday
  - supported timezone aliases
- [x] Keep unknown-place clarification behavior for real time queries

### Step 3 — Preserve shared routing behavior

- [x] Verify that `src/api/skills/policy.py` still enforces the intended route
      precedence after matcher tightening
- [x] Confirm the fix does not break the raw-transcript fallback used by the
      voice bridge wake-stripper recovery path

### Step 4 — Add regression tests first-class

- [x] Extend `tests/test_routing_policy.py` with explicit false-positive guard
      cases for ordinary bunny/photoframe conversation
- [x] Extend `tests/test_time_query.py` with explicit negative coverage for
      `我有時間嗎` / `請問有時間嗎` and simplified equivalents where needed
- [x] Extend local-skill token tests so command-vs-topic boundaries are
      documented in executable form

### Step 5 — Sync docs

- [x] Update `.docs/context.md` with the routing-boundary fix summary and
      verification results
- [x] Update `.docs/product-specs/local-commands.md` because the final matcher
      rules materially changed the documented command surface

### Step 6 — Verification gates

- [x] Run the focused routing/time-query suite first:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q tests/test_time_query.py tests/test_routing_policy.py tests/test_api.py tests/test_voice_bridge_local_routing.py`
- [x] Run the repository suite after edits:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
- [x] Run the full suite:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`

---

## Acceptance Criteria

- [x] `你喜歡兔兔嗎` and `兔兔好可愛` route to `CHAT`, not `LOCAL_SKILL`
- [x] `相框是什麼` and `我想看照片展` route to `CHAT`, not `LOCAL_SKILL`
- [x] `我有時間嗎` and `請問有時間嗎` route to `CHAT`, not `TIME_QUERY`
- [x] Known real local commands still route correctly to `LOCAL_SKILL`
- [x] Known real time/date/weekday queries still route correctly to
      `TIME_QUERY`
- [x] Raw-transcript local-skill fallback still works for wake-stripper loss
      cases
- [x] Updated regression tests pass
- [x] Full test suite passes

---

## Rollback Plan

If matcher tightening introduces regressions:

- revert the token-boundary changes in `src/api/skills/tokens.py`
- revert the conversational-time false-positive guard changes in
  `src/api/skills/time_query.py`
- keep the new regression tests as guardrails
- restore the last known-good routing behavior and re-run the full suite
