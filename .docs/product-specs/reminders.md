# Spec: Reminders

**Module:** `src/api/skills/`, `src/api/app.py`, `src/bridge/voice_bridge.py`, future reminder store modules
**Status:** Planned

---

## Summary

The assistant creates one-time reminders from natural-language requests,
persists them locally, and announces them with voice plus UI state updates when
they become due.

This spec owns reminder creation, normalization, confirmation, persistence, and
delivery behavior.

---

## Goals

- Support one-time reminder creation from natural phrasing.
- Support both absolute and relative reminder times.
- Ask follow-up questions when the parsed time is ambiguous.
- Persist reminders so they survive process restarts.
- Reuse the existing voice bridge and UI state path for due-time delivery.

---

## Supported Reminder Types

### Absolute Reminders
- `今天下午三點提醒我開會`
- `明天早上八點提醒我買咖啡`
- `後天晚上九點提醒我關燈`

### Relative Reminders
- `10 分鐘後提醒我開會`
- `半小時後提醒我喝水`
- `兩小時後提醒我倒垃圾`

### Timezone-Aware Reminders
- `東京時間晚上九點提醒我上線`
- `日本時間明天早上七點提醒我開會`

---

## Expected Behaviour

### Understanding
- The system may use a structured parser to extract reminder intent, target
  time, timezone, task text, and ambiguity markers.
- The parser may improve flexibility, but it must not be the final authority on
  the scheduled timestamp.

### Normalization
- Local code must normalize reminder requests into a single absolute due
  timestamp.
- Relative times must be converted using the system local clock unless the
  request explicitly anchors to another timezone.
- Past timestamps must be rejected.

### Confirmation
- If the requested time is incomplete or ambiguous, the assistant should return
  a clarification question instead of creating a reminder immediately.
- A short-lived pending-confirmation state may be used to resolve the next
  follow-up utterance.

### Delivery
- When a reminder becomes due, the voice bridge should announce it out loud.
- The announcement should also update the shared UI state so the bunny display
  shows the reminder text while speaking.
- A due reminder must be delivered once.

---

## Persistence

- Reminders should be stored locally under `data/`.
- Writes should be atomic.
- Concurrent readers and writers must not duplicate or lose reminders.
- Pending future reminders should survive service restarts.

---

## Expected API Response

### Successful Create

```json
{
  "reply_text": "好，我會在明天早上八點提醒你買咖啡。",
  "meta": {
    "source": "local-skill",
    "action": "create_reminder"
  }
}
```

### Clarification Required

```json
{
  "reply_text": "你是想要明天下午幾點提醒呢？",
  "meta": {
    "source": "local-skill",
    "action": "confirm_reminder"
  }
}
```

---

## Failure Cases

- Missing reminder task text
- Ambiguous time with no safe default
- Unsupported timezone alias
- Past timestamp
- Invalid normalization result
- Store write failure

---

## Relationship To Other Specs

- Time parsing and timezone answer rules live in `time-queries.md`.
- Preference-based defaults such as a remembered default timezone belong in
  `memory.md`.

---

## Open Questions

- What is the exact TTL for pending confirmation state?
- Should reminder confirmation accept `好` / `對` / `不是` style replies, or
  only explicit time clarifications in the first version?
- Should due reminders interrupt ongoing assistant speech or wait for playback
  idle?

---

## Out of Scope

- Recurring reminders
- Calendar integration
- External push notifications
- Cross-device sync
- Long-term conversation memory beyond short confirmation context