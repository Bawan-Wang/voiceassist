# Spec: Local Commands

**Module:** `src/api/skills/` (dispatcher), `src/api/app.py` (entry point)
**Status:** Implemented ✅ (refactored in exec-plan 007)

---

## Summary

Certain commands are handled entirely locally without any LLM call. They are matched by keyword presence in the incoming text and execute a direct system action.

---

## Command: Open Photoframe (a.k.a. Album)

### Trigger Phrases
Any noun token alone is sufficient (verb is optional):

| Object tokens |
|---------------|
| `相框`, `相簿`, `照片`, `photoframe`, `album`, `photos`, `photo frame` |

Examples: `打開相框`、`打開相簿`、`打開照片`、`open photoframe`、`show me the album`

### Action — `src/api/skills/open_photoframe.py::run()`
1. Write `bunny_should_exit=true` to `/tmp/voiceassist_signal.json`
2. Sleep 0.5s so the bunny UI can run its fade-out
3. Hard-kill any leftover bunny / photoframe processes (fallback)
4. Launch `run_photoframe.sh` (which now has a kivy preflight)
5. Wait up to 1.0s for `/tmp/photoframe.ready`
6. If kivy was missing or launch failed → reply: `"相框打不開，可能少裝套件，請看 /tmp/photoframe.log。"`

### Reply (success)
```
好的，已幫你打開相框。
```

### Debounce
Rapid re-triggers within 2.5 s reply with `"已收到，正在切換到相框。"`

---

## Command: Switch to Bunny UI

### Trigger Phrases
Any token alone is sufficient:

| Object tokens |
|---------------|
| `兔兔`, `bunny` |

Examples: `切回兔兔`、`打開bunny`、`switch to bunny`

### Action — `src/api/skills/open_bunny.py::run()`
1. Write `photoframe_should_exit=true` (008 will honour this; 007 still relies on kill-9)
2. Sleep 0.3s
3. Hard-kill any leftover photoframe / bunny processes
4. Clear `bunny_should_exit=false` so the freshly launched bunny doesn't immediately quit
5. Launch `src/ui/assistant_ui.py` with `DISPLAY=:0`

### Reply
```
好的，已切回兔兔助理畫面。
```

### Debounce
2.5 s — rapid re-triggers reply `"已收到，正在切回兔兔。"`

---

## IPC Signal File

`/tmp/voiceassist_signal.json` — atomic-written by skills, polled by UIs.

```json
{
  "bunny_should_exit": false,
  "photoframe_should_exit": false,
  "ts": 1777108412
}
```

| Reader | Path | Behaviour on flag = true |
|--------|------|--------------------------|
| Bunny UI (`src/ui/assistant_ui.py`) | polls every ~0.2s | 0.4s alpha-fade then `sys.exit(0)` |
| Photoframe (`~/workspace/photoframe/main.py`, 008) | daemon thread polls every 0.25s | bounces to Kivy main thread → `Animation(opacity=0, 0.4s)` → `App.stop()` |

Both readers ignore the flag if `ts` was set BEFORE they started, so a
stale signal from a previous session does not immediately kill the new
process.

## Ready file

`/tmp/photoframe.ready` — touched by photoframe `on_start()` after the
Kivy window is up; removed on graceful exit. The `open_photoframe` skill
waits up to 1.5s for it; absence + no live photoframe process → truthful
failure reply (`"相框打不開…"`).

---

## Evaluation Order

Local skills are checked **before** search intent detection and LLM routing,
both in the API (`src/api/app.py`) and in the voice bridge
(`src/bridge/voice_bridge.py::is_local_skill`):

```
Incoming text
      │
      ▼
match_skill(text)?
  YES → skill.run() + return reply (no LLM call)
        meta.source = "local-skill", meta.action = NAME
  NO  → continue to intent-routing.md
```

---

## Out of Scope

- Custom user-defined commands
- Commands requiring confirmation before execution
- Multi-step commands (e.g., "open photoframe and play slideshow")
