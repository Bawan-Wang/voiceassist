# 004 — Fix Voice Bridge Relative Import Crash

## Status: Active 🔴

## Problem

After the `src/` restructure (commit `11b9729`), `rabbitctl.sh start` brings up the bunny UI but voice input is completely dead. Wake word "兔兔助理" gets no response, no LLM call, no TTS playback.

## Root Cause

`src/bridge/voice_bridge.py` uses relative imports:

```python
from .providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider
from .runtime_config import get_selected_provider, load_app_config, resolve_project_path
```

But `rabbitctl.sh` launches it as a **script**, not a module:

```bash
nohup "$PY" -u src/bridge/voice_bridge.py "${voice_args[@]}" >/tmp/voice_bridge.log 2>&1 &
```

Relative imports (`from .x`) require the file to be loaded inside a package context. When run as a script, Python sets `__package__ = None` and the import fails immediately at startup:

```
ImportError: attempted relative import with no known parent package
```

The process dies before binding to the microphone, so no audio is ever captured.

## Evidence

`/tmp/voice_bridge.log`:
```
Traceback (most recent call last):
  File "/home/jh-pi/.openclaw/workspace/voiceassist/src/bridge/voice_bridge.py", line 41, in <module>
    from .providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider
ImportError: attempted relative import with no known parent package
```

`./rabbitctl.sh status`:
```
api: stopped
bunny_ui: stopped
voice_bridge: stopped
```

(Note: api/ui also stopped here because user re-ran status after the failure.)

## Fix Options

### Option A — Launch as a module (preferred, matches API style)

Change `rabbitctl.sh`:

```bash
# Before
nohup "$PY" -u src/bridge/voice_bridge.py "${voice_args[@]}" ...

# After
nohup "$PY" -u -m src.bridge.voice_bridge "${voice_args[@]}" ...
```

`PYTHONPATH="$BASE_DIR"` is already exported, so `src.bridge.voice_bridge` resolves correctly. Also need to update `kill_all` and `status` pgrep patterns to match the new command line.

### Option B — Revert to absolute imports

Change `src/bridge/voice_bridge.py`:

```python
from src.bridge.providers import PiperTextToSpeechProvider, SherpaOnnxSpeechToTextProvider
from src.bridge.runtime_config import get_selected_provider, load_app_config, resolve_project_path
```

Less idiomatic but requires no shell script change.

**Recommendation: Option A** — keeps imports clean and matches how `src.api.app` is already launched (`uvicorn src.api.app:app`).

## Action Items

- [ ] Update `rabbitctl.sh`:
  - [ ] Replace `src/bridge/voice_bridge.py` launch with `-m src.bridge.voice_bridge`
  - [ ] Update `kill_all` pkill pattern: `src/bridge/voice_bridge.py` → `src.bridge.voice_bridge`
  - [ ] Update `status` pgrep pattern accordingly
- [ ] Also check `src/ui/assistant_ui.py` — does it have any relative imports? If yes, apply same fix
- [ ] Run `./rabbitctl.sh restart` and verify all 3 services show running in `status`
- [ ] Verify `/tmp/voice_bridge.log` shows successful audio device init (no traceback)
- [ ] Live test: say "兔兔助理 你好" and verify TTS reply
- [ ] Run `pytest tests/ -v` — must still pass (22/22)
- [ ] Commit with message: `fix: launch voice_bridge as module to support relative imports`

## Acceptance Criteria

- ✅ `./rabbitctl.sh start` shows all 3 services running
- ✅ `/tmp/voice_bridge.log` shows audio init logs, no ImportError
- ✅ Saying "兔兔助理" triggers UI state change to `listening` and TTS reply
- ✅ All existing tests still pass
