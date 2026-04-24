# Spec: Local Commands

**Module:** `src/api/app.py`
**Status:** Implemented ✅

---

## Summary

Certain commands are handled entirely locally without any LLM call. They are matched by keyword presence in the incoming text and execute a direct system action.

---

## Command: Open Photoframe

### Trigger Phrases
Command must contain **both** a verb token and an object token:

| Verb tokens | Object tokens |
|-------------|---------------|
| `打開`, `開啟` | `相框`, `photoframe` |

Examples: `打開相框`、`幫我開啟photoframe`

### Action
Calls `open_photoframe()` in `src/api/app.py`:
- Launches `run_photoframe.sh` as a background subprocess
- Kills any existing photoframe process first (debounced)

### Reply
```
好的，已幫你打開相框。
```

### Debounce
- Rapid repeated triggers within the debounce window are ignored
- Prevents multiple photoframe processes from launching

---

## Command: Switch to Bunny UI

### Trigger Phrases
Command must contain **both** a verb token and an object token:

| Verb tokens | Object tokens |
|-------------|---------------|
| `打開`, `開啟`, `切回` | `兔兔`, `bunny` |

Examples: `切回兔兔`、`打開bunny`、`開啟兔兔助理畫面`

### Action
Calls `open_bunny_ui()` in `src/api/app.py`:
- Kills any existing bunny UI process
- Re-launches `src/ui/assistant_ui.py` as a background subprocess with `DISPLAY=:0`

### Reply
```
好的，已切回兔兔助理畫面。
```

### Debounce
- Same debounce guard as photoframe — rapid triggers are ignored

---

## Evaluation Order

Local commands are checked **before** search intent detection and LLM routing:

```
Incoming text
      │
      ▼
Match local command?
  YES → execute + return reply (no LLM call)
  NO  → continue to intent-routing.md
```

---

## Out of Scope

- Custom user-defined commands
- Commands requiring confirmation before execution
- Multi-step commands (e.g., "open photoframe and play slideshow")
