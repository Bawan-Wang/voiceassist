# Spec: Reminders

**Module:** `src/api/skills/`, `src/api/app.py`, `src/bridge/voice_bridge.py`, `src/api/skills/reminder_store.py`
**Status:** Implemented ✅

---

## Summary

The assistant creates one-time reminders from natural-language requests,
normalizes reminder times deterministically in local code, persists reminders
under `data/`, and announces due reminders through the existing voice bridge
plus UI state path.

This spec owns reminder creation, normalization, confirmation, persistence, and
delivery behavior.

This behavior was implemented in exec-plan 022 and is now the current runtime
behavior.

---

## Product Boundaries

- First version is single-device, single-user, with one global reminder store
  and one global pending-confirmation state.
- First version supports one-time reminders only.
- Reminder delivery reuses the current voice bridge plus
  `voiceBridge.state_path` UI contract.
- Reminder creation may be completed in one turn or through the bounded
  confirmation flows defined below.
- This spec does not add memory-driven defaults, recurring reminders, calendar
  integration, external push delivery, or per-user/session isolation.

---

## Goals

- Support one-time reminder creation from natural phrasing.
- Support both absolute and relative reminder times.
- Ask follow-up questions when the parsed time is ambiguous.
- Persist reminders so they survive process restarts.
- Reuse the existing voice bridge and UI state path for due-time delivery.

---

## Supported Reminder Requests

### Absolute Reminders

- `今天下午三點提醒我開會`
- `明天早上八點提醒我買咖啡`
- `後天晚上九點提醒我關燈`

Rules:

- A v1 absolute reminder must contain task text plus a deterministic date anchor
  and clock time.
- Supported day anchors in v1 are `今天`, `明天`, and `後天`.
- Supported day-part words in v1 include `早上`, `上午`, `中午`, `下午`, and
  `晚上`.

### Relative Reminders

- `5 秒鐘後提醒我吃藥`
- `10 分鐘後提醒我開會`
- `半小時後提醒我喝水`
- `兩小時後提醒我倒垃圾`

Rules:

- v1 relative reminders support second/minute/hour duration math.
- Supported relative forms are:
  - `N 秒鐘後`
  - `N 分鐘後`
  - `半小時後`
  - `N 小時後`
- v1 does not support `一週後`, recurring schedules, or fuzzy phrases such as
  `晚點提醒我`.

### Timezone-Aware Clock Reminders

- `東京時間晚上九點提醒我上線`
- `日本時間明天早上七點提醒我開會`

Rules:

- Timezone-aware support applies to clock-time reminders, not pure relative
  durations.
- Named timezone/place aliases must reuse the same curated alias scope defined
  in `time-queries.md`.
- Unknown timezone aliases must not be guessed.

### Reminder Follow-Up Utterances

Examples:

- first turn: `明天下午提醒我開會`
  follow-up: `三點`
- first turn: `晚上九點提醒我收衣服` spoken after that same day's 9 PM has
  already passed
  follow-up: `對`

---

## Route Ownership And Precedence

The current shared `classify_request(...)` order is:

1. local skill
2. reminder
3. time query
4. tool-needed/search
5. chat

Reminder routing must outrank time queries because reminder phrases can contain
time-query words and timezone labels such as `東京時間`, but the presence of
`提醒我` means the utterance is not asking for the current time.

Ownership split:

- `src/api/app.py` owns reminder creation, clarification/cancel responses, and
  the JSON response contract.
- `src/bridge/voice_bridge.py` owns due-reminder delivery and the voice-side
  pending-follow-up bypass.
- When a global pending reminder confirmation exists, short follow-up utterances
  such as `三點` or `對` must be routed to reminder resolution before normal
  stateless classification.

---

## Deterministic Reminder Outcomes

The reminder parser/normalizer must end in exactly one of these outcomes:

1. immediate create
2. clarification required (`need_time_detail`)
3. candidate confirmation required (`confirm_candidate`)
4. rejection

The parser may interpret raw text, but the final stored reminder must always be
produced by local deterministic normalization code.

### Immediate Create

Create the reminder immediately when the first utterance already contains:

- reminder intent,
- task text,
- a deterministic due time,
- and a resolvable timezone context.

Examples:

- `5 秒鐘後提醒我吃藥`
- `明天早上八點提醒我買咖啡`
- `10 分鐘後提醒我開會`

### Clarification Required — `need_time_detail`

Use this mode when the task is clear and the day anchor is clear, but the final
clock time is missing or incomplete.

Example:

- first turn: `明天下午提醒我開會`
- reply: `你想要明天下午幾點提醒呢？`

Rules:

- This mode opens a 60-second pending-confirmation state.
- Accepted follow-up content is explicit time information only.
- `好` / `對` / `不是` do not resolve this mode.

### Candidate Confirmation Required — `confirm_candidate`

Use this mode only when the utterance contains a complete clock time but no
explicit day anchor, and the same-day candidate has already passed. In that
case the assistant may propose the next occurrence and ask for yes/no before
creating the reminder.

Example:

- current local time: 22:00
- first turn: `晚上九點提醒我收衣服`
- reply: `現在已經過了今天晚上九點，你是要我明天晚上九點提醒你嗎？`

Rules:

- This mode opens a 60-second pending-confirmation state.
- Accepted follow-up content is:
  - yes tokens such as `好`, `對`, `是` and common simplified equivalents
    such as `对`
  - no/cancel tokens such as `不是`, `不對`, `不对`, `不用了`, `取消`, `算了`
  - an explicit replacement time phrase, which replaces the proposed candidate
- This mode is the only v1 reminder flow that accepts bare yes/no replies.

### Rejection

Reject instead of creating a reminder when the request is incomplete in a way
that v1 does not carry across turns, or when the normalized result is invalid.

Examples:

- missing task text
- unsupported timezone alias
- explicit past timestamp
- invalid normalization result
- store write failure

---

## Time Normalization Rules

- The final reminder timestamp must be normalized to one absolute `due_at`
  instant in UTC ISO 8601 form.
- Each reminder record must also keep the resolved timezone name and a spoken
  label for truthful replies.
- Absolute reminders without an explicit timezone use the local runtime
  timezone, which is currently `Asia/Taipei`.
- `今天`, `明天`, and `後天` are evaluated in the resolved timezone context.
- Relative second/minute/hour reminders use local deterministic `timedelta` math from
  the system clock.
- Pure relative reminders do not need a timezone alias because a duration maps
  to the same absolute instant regardless of display timezone.
- If the user explicitly anchors the day and the resolved timestamp is already
  in the past, reject the request and ask for a new time. Do not silently roll
  it forward.
- If the user gives a full clock time without an explicit day anchor and that
  same-day candidate has already passed, the assistant may propose the next
  occurrence through `confirm_candidate`.
- Unknown place names must not fall back to the local timezone.
- Incomplete time phrases must not be guessed.

---

## Pending Confirmation Contract

Pending reminder confirmation lives in `data/reminder_pending.json`.

Rules:

- At most one global pending reminder confirmation may exist at a time.
- Absence of the file means there is no pending reminder confirmation.
- The pending record must be written atomically.
- The pending record must carry normalized context, not only raw text, so a
  follow-up utterance does not have to reconstruct the first turn from scratch.
- Required stored fields are:
  - `mode`
  - `original_text`
  - `task_text`
  - `timezone`
  - `timezone_label`
  - `created_at`
  - `expires_at`
  - mode-specific normalized context such as a partial day/time frame or a
    concrete `candidate_due_at`
- TTL is fixed at 60 seconds.
- Expired pending state must be cleared before processing the next utterance.

Reminder follow-up rules:

- If the follow-up resolves the pending state, create the reminder and clear the
  pending record.
- If the follow-up declines the candidate, clear the pending record and return a
  cancel reply.
- If the follow-up cannot resolve the pending state, clear the pending record
  and then re-run normal routing on the same utterance so the user is not
  trapped in reminder mode.

---

## Persistence Contract

Durable reminders live in `data/reminders.json`.

Recommended shape:

```json
{
  "version": 1,
  "reminders": [
    {
      "id": "rmd_20260517_001",
      "task_text": "買咖啡",
      "source_text": "明天早上八點提醒我買咖啡",
      "timezone": "Asia/Taipei",
      "timezone_label": "台灣",
      "due_at": "2026-05-18T00:00:00+00:00",
      "created_at": "2026-05-17T08:00:00+00:00",
      "status": "pending",
      "delivered_at": null
    }
  ]
}
```

Rules:

- All writes must be atomic.
- Readers and writers must tolerate the file not existing yet.
- Timestamps in the store must be timezone-aware ISO 8601 values.
- `status` is `pending` until delivery succeeds, then becomes `delivered`.
- `delivered_at` remains `null` until playback completes successfully.
- Durable reminders and pending confirmation must stay in separate files to
  reduce contention between creation and due-delivery updates.

---

## Due Delivery Behavior

Due reminder delivery is owned by `src/bridge/voice_bridge.py`.

Rules:

- The voice bridge should run a lightweight background reminder poller.
- v1 delivery is idle-only: due reminders must wait until the bridge is not in
  the middle of listening, thinking, or speaking.
- Due reminders must be delivered oldest-first by `due_at`.
- Startup recovery must deliver already-overdue reminders oldest-first after the
  bridge reaches idle.
- Spoken reminder format in v1 should be short and truthful, for example:
  `提醒你，買咖啡。`
- Immediately before playback, the bridge should update the shared UI state with
  `phase="speaking"`, `userText=""`, and `assistantText=<delivery text>`.
- After playback finishes, the bridge should update the UI back to
  `phase="idle"` while keeping the last spoken reminder text visible.
- A reminder must be marked delivered only after playback returns successfully.
- If synthesis or playback fails, the reminder must remain undelivered so it can
  be retried later. The implementation may apply a short retry backoff, but it
  must not drop the reminder silently.

---

## Expected API Response

All reminder create/confirm/cancel responses stay on the deterministic
`local-skill` path.

### Successful Create

```json
{
  "reply_text": "好，我會在明天早上八點提醒你買咖啡。",
  "meta": {
    "source": "local-skill",
    "action": "create_reminder",
    "reminder_id": "rmd_20260517_001",
    "due_at": "2026-05-18T00:00:00+00:00",
    "timezone": "Asia/Taipei"
  }
}
```

### Clarification Required — Missing Time Detail

```json
{
  "reply_text": "你想要明天下午幾點提醒呢？",
  "meta": {
    "source": "local-skill",
    "action": "confirm_reminder",
    "confirmation_mode": "need_time_detail",
    "expires_at": "2026-05-17T12:01:00+00:00",
    "candidate_due_at": null,
    "timezone": "Asia/Taipei"
  }
}
```

### Clarification Required — Candidate Confirmation

```json
{
  "reply_text": "現在已經過了今天晚上九點，你是要我明天晚上九點提醒你嗎？",
  "meta": {
    "source": "local-skill",
    "action": "confirm_reminder",
    "confirmation_mode": "confirm_candidate",
    "expires_at": "2026-05-17T12:01:00+00:00",
    "candidate_due_at": "2026-05-18T13:00:00+00:00",
    "timezone": "Asia/Taipei"
  }
}
```

### Pending Reminder Cancelled Or Declined

```json
{
  "reply_text": "好，那我先不建立這個提醒。",
  "meta": {
    "source": "local-skill",
    "action": "cancel_reminder"
  }
}
```

### Rejected Request

```json
{
  "reply_text": "現在這個時間已經過了，請再說一個新的提醒時間。",
  "meta": {
    "source": "local-skill",
    "action": "create_reminder",
    "reminder_status": "rejected",
    "reason": "past_time"
  }
}
```

Suggested `reason` values in v1:

- `missing_task`
- `unknown_timezone`
- `past_time`
- `invalid_time`
- `store_write_failed`

---

## Failure And Clarification Rules

- Missing task text is rejected in v1 instead of opening a third follow-up mode.
  The reply should ask the user to restate the reminder with the task included.
- Unknown timezone aliases return a clarification-style reply, but v1 does not
  keep an active pending state for unsupported place names. The user should
  restate the full reminder with a supported timezone/place alias.
- Empty or expired pending reminder state must not hijack unrelated later
  utterances.
- Store write failures must return a truthful error reply on the local-skill
  path.

---

## Relationship To Other Specs

- Time parsing and timezone alias rules live in `time-queries.md` and should be
  reused instead of duplicated.
- Long-term preference defaults such as remembered timezone preferences belong
  in `memory.md`, not in v1 reminders.

---

## Acceptance Criteria

- The finalized implementation supports one-time absolute reminders, second/minute/hour
  relative reminders, and timezone-aware clock reminders.
- Reminder routing precedes time-query/search/chat routing once reminder intent
  is implemented.
- Pending reminder confirmation is limited to the two defined modes,
  `need_time_detail` and `confirm_candidate`, with a 60-second TTL.
- Bare yes/no follow-ups are accepted only for `confirm_candidate`.
- Reminder state survives process restarts through durable JSON storage under
  `data/`.
- Due reminders are delivered by the voice bridge only when the bridge is idle.
- Overdue reminders are drained oldest-first after restart.
- A reminder is marked delivered only after successful playback completion.
- API replies use the documented local-skill metadata contract.

---

## Test Matrix

The implementation plan should cover at least these test slices:

- reminder parser/normalizer unit tests for:
  - absolute reminders
  - relative reminders
  - timezone-aware reminders
  - `need_time_detail`
  - `confirm_candidate`
  - past-time rejection
- reminder store tests for:
  - atomic create/update behavior
  - pending-state TTL handling
  - restart-safe durable reads
- routing-policy tests proving reminder precedence over time-query/search/chat
- API tests for:
  - immediate create
  - clarification response metadata
  - cancel/decline path
  - truthful rejection replies
- voice-bridge tests for:
  - pending-follow-up bypass
  - idle-only due delivery
  - overdue reminder drain order on startup

---

## Out of Scope

- Recurring reminders
- Calendar integration
- External push notifications
- Cross-device sync
- Long-term conversation memory beyond short confirmation context