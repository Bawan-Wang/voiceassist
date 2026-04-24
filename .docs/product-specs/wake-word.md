# Spec: Wake Word Detection

**Module:** `src/bridge/voice_bridge.py`
**Status:** Implemented ✅

---

## Summary

The assistant continuously listens for a wake word before processing any command. A three-tier matching strategy ensures robust recognition despite misheard or variant pronunciations.

---

## Primary Wake Word

| | Value |
|---|---|
| Default | `兔兔助理` |
| Configurable via | `config.yaml → voiceBridge.wake.primary` or `--wake` CLI flag |

---

## Wake Word Variants

The following alternatives are accepted as equivalent to the primary wake word:

| Variant | Type |
|---|---|
| `兔兔助手` | Near-synonym |
| `兔兔兔` | Abbreviated |
| `兔兔` | Shortened |
| `bunny assistant` | English equivalent |
| `bunny helper` | English alternative |
| `zero` | Codename alias |
| `圖圖助理` | Common mishear |
| `嘟嘟助理` | Common mishear |
| `處處助理` | Common mishear |
| `兔兔處理` | Common mishear |
| `兔兔注意` | Common mishear |
| `杜兔助理` | Common mishear |
| `嘟兔助理` | Common mishear |
| `圖兔助理` | Common mishear |

---

## Three-Tier Matching Logic

Evaluated in order — first match wins:

### Tier 1 — Exact / Contains Match
- Transcript contains the primary wake word string or any variant → **match**

### Tier 2 — Token-Combo Fallback
- Transcript contains at least one **rabbit token** (`兔`, `圖`, `嘟`, `bunny`, `zero`) **AND** at least one **helper token** (`助理`, `助手`, `assistant`, `helper`) → **match**

### Tier 3 — Fuzzy Match
- `difflib.SequenceMatcher` ratio between transcript and primary wake word ≥ **0.70** → **match**

---

## Two-Step Wake Flow

```
User says wake word
        │
        ▼
UI state → "listening"
        │
        ▼
Wait up to 1.2s for follow-up command utterance
        │
   ┌────┴────┐
command    no command
received   in time
   │            │
route       return to idle
intent
```

---

## Auto-Route Without Wake

In certain conditions a command is routed **without** requiring the wake word:

| Condition | Behaviour |
|---|---|
| Transcript contains a command keyword | Route directly |
| Transcript length ≥ 8 characters | Route directly |

A **2.0s cooldown** is enforced between auto-route triggers to prevent duplicate firing.

---

## Out of Scope

- Speaker verification / voiceprint authentication
- Per-user custom wake words
- Always-on cloud wake word engine
