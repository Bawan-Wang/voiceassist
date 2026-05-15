# Spec: Memory

**Module:** future memory/profile modules plus integration points in skills and routing
**Status:** Planned

---

## Summary

The assistant may remember a limited set of user preferences and explicit
profile-style facts that improve later time and reminder interactions.

This spec starts with narrow, controllable memory. It does not assume full
conversation memory.

---

## Goals

- Let the assistant remember a small set of useful user preferences.
- Make remembered preferences influence future behavior in predictable ways.
- Keep write behavior explicit and auditable.
- Avoid turning the assistant into an unbounded conversation-history system in
  the first phase.

---

## Initial Memory Scope

### Preference Memory
- Preferred timezone
- Preferred way to be addressed
- Default reminder style or phrasing preferences

### Explicit User Facts
- Facts the user intentionally asks the assistant to remember
- Facts that are safe, narrow, and clearly attributable to one user profile

---

## Expected Behaviour

### Writing Memory
- Memory writes should happen from explicit user intent, for example:
  - `記住我習慣看日本時間`
  - `以後叫我阿傑`
- The first version should avoid silently inferring durable memory from casual
  conversation.

### Applying Memory
- A remembered preferred timezone may affect default time answers when no
  explicit timezone is requested.
- A remembered display name may affect spoken replies.
- Reminder defaults may use stored preferences only when doing so does not make
  the result ambiguous or unsafe.

### Updating And Deleting Memory
- Users should be able to inspect, overwrite, or delete remembered preferences.
- If a remembered value conflicts with a new explicit request, the explicit
  request should win.

---

## Example Triggers

### Write
- `記住我習慣看日本時間`
- `以後提醒我都用早上八點這種講法`
- `叫我小杰`

### Read / Apply
- `我預設時區是什麼？`
- `我剛剛叫你記住什麼？`

### Delete / Reset
- `忘掉我喜歡日本時間`
- `不要再叫我小杰`

---

## Expected API Response

```json
{
  "reply_text": "好，我記住你比較常看日本時間。",
  "meta": {
    "source": "local-skill",
    "action": "write_memory"
  }
}
```

The exact response contract for memory read, write, and delete operations still
needs to be finalized.

---

## Safety And Scope Rules

- Durable memory should be narrow and intentional.
- The assistant should not claim to remember arbitrary long-form conversation
  history unless that behavior is explicitly designed and implemented later.
- Memory categories should be enumerated rather than open-ended in the first
  phase.

---

## Relationship To Other Specs

- Time defaults and timezone preferences interact with `time-queries.md`.
- Reminder defaults and preference reuse interact with `reminders.md`.

---

## Open Questions

- Which memory categories belong in the first shipped version?
- Should memory writes require explicit confirmation for every category, or only
  for certain durable facts?
- How should memory inspection be phrased in spoken replies so it stays short?

---

## Out of Scope

- Full multi-turn conversation memory
- Summarizing the entire dialogue history
- Cross-device account sync
- Automatic inference of long-term personal facts from casual chat