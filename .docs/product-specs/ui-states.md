# Spec: UI States

**Module:** `src/ui/assistant_ui.py`, `src/api/app.py`
**Status:** Implemented ✅

---

## Summary

The bunny face UI (`assistant_ui.py`) reflects the assistant's current activity through four visual states. State is communicated via a shared JSON file polled by the UI process.

---

## Shared State Contract

**File:** `data/demo_state.json` (gitignored, created at runtime)

```json
{
  "phase": "idle | listening | thinking | speaking",
  "userText": "what the user said",
  "assistantText": "what the assistant replied"
}
```

| Field | Written by | Read by |
|-------|-----------|---------|
| `phase` | `src/api/app.py` | `src/ui/assistant_ui.py` |
| `userText` | `src/api/app.py` | `src/ui/assistant_ui.py` |
| `assistantText` | `src/api/app.py` | `src/ui/assistant_ui.py` |

---

## State Definitions

### `idle`
| Property | Value |
|----------|-------|
| Trigger | Default state; reply finished or no activity |
| Display color | `#FFFFFF` (white) |
| Background | `#10121a` |
| UI behaviour | Bunny face resting animation |

### `listening`
| Property | Value |
|----------|-------|
| Trigger | Wake word detected, waiting for command |
| Display color | `#FFE29A` (warm yellow) |
| Background | `#10121a` |
| UI behaviour | Bunny face attentive / ears up |

### `thinking`
| Property | Value |
|----------|-------|
| Trigger | Command received, LLM/agent call in progress |
| Display color | `#E3C9FF` (soft purple) |
| Background | `#10121a` |
| UI behaviour | Bunny face processing animation |

### `speaking`
| Property | Value |
|----------|-------|
| Trigger | TTS playback started |
| Display color | `#BFF3C1` (soft green) |
| Background | `#10121a` |
| UI behaviour | Bunny face speaking animation |

---

## State Transition Flow

```
idle
 │
 │  wake word detected
 ▼
listening
 │
 │  command received
 ▼
thinking
 │
 │  reply ready, TTS starts
 ▼
speaking
 │
 │  TTS playback complete
 ▼
idle
```

---

## Display Configuration

From `config.yaml → display`:

| Parameter | Value |
|-----------|-------|
| Resolution | 1280 × 720 |
| Fullscreen | `false` |
| Target FPS | 60 |
| Poll interval | UI polls `demo_state.json` each frame |

---

## Out of Scope

- Multiple simultaneous UI clients
- WebSocket-based push updates (currently file-poll only)
- Mobile / web UI
