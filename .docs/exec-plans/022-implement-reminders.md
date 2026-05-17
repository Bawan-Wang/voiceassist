# 022 — Implement One-Time Reminders

## Status: Active

## Motivation

Phase 22 in [PLAN.md](../../PLAN.md) defines the next capability sequence as:

1. Time queries
2. Reminders
3. Memory

Time queries landed in exec-plan 021 as the first deterministic time surface.
The next slice is one-time reminders, which depend on the same time semantics
but add three new responsibilities:

- bounded multi-turn clarification,
- durable persistence,
- and out-of-band due-time delivery through the voice bridge.

The target product behavior is now locked in
[product-specs/reminders.md](../product-specs/reminders.md). This exec-plan is
the implementation plan for that spec.

---

## Scope

In scope:

- one-time reminder creation from absolute and relative reminder phrasing
- deterministic local time normalization
- the two bounded pending-confirmation modes:
  - `need_time_detail`
  - `confirm_candidate`
- durable reminder storage under `data/`
- idle-only due-reminder delivery through `src/bridge/voice_bridge.py`
- tests and docs needed to keep the new reminder path maintainable

Out of scope:

- recurring reminders
- reminder list/edit/delete flows
- calendar integration
- external push notifications
- memory-driven defaults
- per-user or per-client reminder state

---

## User Decisions (locked)

| Question | Choice |
|---|---|
| Reminder scope | Single device, single user, one global reminder store |
| Relative time support | Included in v1 |
| Relative-time range | Minutes and hours only |
| Pending confirmation TTL | 60 seconds |
| Missing-time follow-up | Explicit time content required |
| Bare yes/no follow-up | Allowed only for `confirm_candidate` |
| Due reminder interruption | Do not interrupt active voice interaction; wait for idle |

---

## Pre-flight

- [ ] Confirm [product-specs/reminders.md](../product-specs/reminders.md) is the
      finalized source of truth.
- [ ] Snapshot the current baseline suite:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [ ] Confirm there is no active overlapping reminder implementation branch or
      unmerged reminder module under `src/api/skills/`.
- [ ] Re-read the current time-query implementation in
      [src/api/skills/time_query.py](../../src/api/skills/time_query.py) before
      adding reminder time parsing so timezone alias behavior does not drift.

---

## Target Behavior

For reminder intents defined by the finalized spec:

- complete one-turn reminder requests create a durable reminder immediately,
- incomplete-but-supported reminder requests enter one of the two bounded
  clarification modes,
- pending reminder follow-ups bypass normal chat/search/time-query routing,
- due reminders are spoken by the voice bridge only when it is idle,
- and overdue reminders survive restart and are delivered oldest-first.

---

## Action Items

### Step 1 — Add deterministic reminder parsing and normalization

- [ ] Add a dependency-light reminder module under `src/api/skills/`.
- [ ] Parse reminder intent, task text, and time shape for:
  - absolute reminders,
  - relative minute/hour reminders,
  - timezone-aware clock reminders.
- [ ] Reuse or extract the curated timezone alias table from the time-query
      implementation instead of copying it into a second independent table.
- [ ] Represent the parser result as explicit local-code outcomes:
  - immediate create,
  - `need_time_detail`,
  - `confirm_candidate`,
  - rejection.

### Step 2 — Add durable reminder and pending-confirmation storage

- [ ] Add atomic JSON store helpers for:
  - `data/reminders.json`
  - `data/reminder_pending.json`
- [ ] Keep durable reminders and short-lived pending state in separate files.
- [ ] Store timestamps as timezone-aware ISO 8601 values.
- [ ] Ensure absent files are treated as empty state, not hard failures.

### Step 3 — Extend shared routing policy with reminder precedence

- [ ] Add a reminder route kind to `src/api/skills/policy.py`.
- [ ] Lock the new route order to:
  1. local skill
  2. reminder
  3. time query
  4. tool-needed/search
  5. chat
- [ ] Add guard coverage proving reminder phrases that contain time/timezone
      words do not fall into the time-query route.

### Step 4 — Wire the API execution path

- [ ] Update `src/api/app.py` so `POST /zero-assistant` can:
  - create reminders,
  - emit clarification replies,
  - accept pending reminder follow-ups,
  - return truthful rejection replies.
- [ ] Preserve the existing `AssistResponse` envelope.
- [ ] Return `meta.source="local-skill"` for reminder create/confirm/cancel
      responses.

### Step 5 — Wire the voice bridge for pending follow-ups and due delivery

- [ ] Update `src/bridge/voice_bridge.py` so an active pending reminder state
      is checked before normal stateless classification.
- [ ] Keep wake-word handling, `_should_route_without_wake()`, and audio
      capture behavior unchanged.
- [ ] Add a lightweight background due-reminder poller.
- [ ] Deliver due reminders only when the bridge is idle.
- [ ] Reuse `update_state(...)` and `speak(...)` for delivery UI/audio behavior.
- [ ] Mark reminders delivered only after successful playback completion.

### Step 6 — Add reminder-focused tests

- [ ] Add parser/normalizer unit coverage in a new reminder test file.
- [ ] Add store tests covering atomic writes, TTL expiry, and durable reload.
- [ ] Extend `tests/test_routing_policy.py` with reminder precedence cases.
- [ ] Extend `tests/test_api.py` with reminder create/confirm/cancel/reject
      coverage.
- [ ] Add voice-bridge reminder tests for:
  - pending-follow-up bypass,
  - idle-only delivery,
  - overdue oldest-first drain behavior.

### Step 7 — Sync docs after behavior lands

- [ ] Update [product-specs/intent-routing.md](../product-specs/intent-routing.md)
      so the documented route tree includes reminders in the correct position.
- [ ] Update [context.md](../context.md) with implementation notes and final
      verification results.
- [ ] Update technical docs only if the final implementation materially changes
      the current voice-vs-HTTP entrypoint explanation.

### Step 8 — Verify in layers

- [ ] Run the new reminder unit/store tests first.
- [ ] Run the reminder routing/API/voice slice next.
- [ ] Run the required repository suite after editing `src/api/app.py` and
      `src/bridge/voice_bridge.py`:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest tests/ -v`
- [ ] Run the full suite:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [ ] If the user explicitly approves a live smoke, run one short reminder
      create-and-deliver manual pass without restarting unrelated services.

---

## Acceptance Criteria

- [ ] One-turn absolute reminders create durable reminder records.
- [ ] One-turn relative minute/hour reminders create durable reminder records.
- [ ] Reminder phrases with timezone labels route to the reminder path, not the
      time-query path.
- [ ] `need_time_detail` and `confirm_candidate` both work with a 60-second TTL.
- [ ] Bare yes/no follow-ups are accepted only for `confirm_candidate`.
- [ ] Missing-task, unknown-timezone, invalid-time, past-time, and store-write
      failures return truthful local-skill replies.
- [ ] Pending reminder follow-ups bypass normal routing in the voice bridge.
- [ ] Due reminders are delivered oldest-first only when the bridge is idle.
- [ ] Overdue reminders survive restart and are delivered after startup.
- [ ] The full test suite passes.

---

## Rollback Plan

If reminder changes introduce regressions:

- remove `RouteKind.REMINDER` from the shared classifier,
- disable pending reminder follow-up handling,
- disable the voice-bridge due-reminder poller,
- keep the new tests as guardrails,
- and restore the last known-good local-skill/time-query/search/chat behavior.