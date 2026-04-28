# 013 — Consolidate Skill Process Helpers and Shared Constants

## Status: Done ✅ (live-verified 2026-04-28)

## Motivation

The post-011 audit (re-confirmed during 012 wrap-up) flagged a second
chunk of low-risk redundancy inside `src/api/skills/`:

- The five process helpers — `_pids`, `_count`, `_kill_all`,
  `_kill_pidfile`, `_alive_from_pidfile` — are **byte-for-byte
  identical** in `open_photoframe.py` (lines 29–81) and `open_bunny.py`
  (lines 28–78). Any future fix has to be applied twice.
- Three constants (`VOICE_DIR`, `PHOTO_PID`, `BUNNY_PID`) are duplicated
  literals across the same two files.
- `SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")` is defined in
  `src/api/skills/_signal.py` (the canonical source) **and again** in
  `src/ui/assistant_ui.py` line ~296 — a copy-paste that has already
  drifted once historically.

This plan extracts the duplicates into two new private modules under
`src/api/skills/` and switches `assistant_ui.py` to import the canonical
`SIGNAL_PATH`. **Zero behaviour change** — purely an internal refactor.

Out of scope (deferred to other plans):

- 014: unify `SEARCH_TOKENS` between `app.py` and `voice_bridge.py`.
- `_LAST` debounce centralisation (per-skill semantics intentionally
  preserved here).
- `AssistRequest.language` / `source` unused fields, `DEFAULT_VOICE`
  typo, wake-strip length fallback (tracked in `.docs/tech-debt.md`).

---

## Pre-flight

- [ ] Confirm 012 has shipped to `origin/main`:
      `git log --oneline | grep 012` → expect `8a179a0`.
- [ ] Snapshot baseline tests: `.venv/bin/pytest -q` → expect **65 passed**.
- [ ] `git status -s` clean.

---

## Phase A — Extract shared internals

Steps in this phase are independent and can be done in any order.

### Step 1 — Create `src/api/skills/_paths.py`

New module containing only the three duplicated constants, copied
verbatim from the current `open_photoframe.py`:

```python
"""Shared filesystem paths for skill modules.

Kept as a tiny, dependency-free module so it can be imported from any
skill without dragging in subprocess / signal logic.
"""

from pathlib import Path

VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
```

### Step 2 — Create `src/api/skills/_process_utils.py`

Move the five helpers byte-for-byte from `open_photoframe.py`
(lines 29–81). Keep the same imports they currently rely on
(`os`, `subprocess`, `pathlib.Path`).

```python
"""Process / PID-file helpers shared by skill launchers.

Internal API: not part of the public skills package surface.
"""

import os
import subprocess
from pathlib import Path

# ---- copy of _pids / _count / _kill_all / _kill_pidfile /
#      _alive_from_pidfile (verbatim from open_photoframe.py 29-81) ----
```

The functions stay name-prefixed with `_` because they remain
package-private; the two skill modules will import them explicitly.

---

## Phase B — Refactor skill modules (depends on Phase A)

### Step 3 — Update `src/api/skills/open_photoframe.py`

- Replace lines 29–81 (five helpers) with:
  ```python
  from ._process_utils import (
      _pids,
      _count,
      _kill_all,
      _kill_pidfile,
      _alive_from_pidfile,
  )
  ```
- Replace the local `VOICE_DIR` / `PHOTO_PID` / `BUNNY_PID` definitions
  (lines 16, 18, 19) with:
  ```python
  from ._paths import VOICE_DIR, PHOTO_PID, BUNNY_PID
  ```
  Keep the names module-local so existing
  `monkeypatch.setattr(open_photoframe, "PHOTO_PID", ...)` calls in the
  tests continue to work without modification.
- Drop now-unused `import subprocess` (only the helpers used it).
- Drop now-unused `import os` **only if** no other usage remains
  (verify: it is also used in `os.kill` inside helpers, which are now
  imported, so `os` should be removable — confirm with grep).
- Keep untouched: `PHOTOFRAME_SCRIPT`, `PHOTO_LOG`, `PHOTO_READY`,
  `PHOTO_CMD`, `_LAST`, `match()`, `run()`.

### Step 4 — Update `src/api/skills/open_bunny.py`

Same pattern as Step 3:

- Helpers (lines 28–78) → `from ._process_utils import ...`
- `VOICE_DIR` / `PHOTO_PID` / `BUNNY_PID` → `from ._paths import ...`
- Drop `subprocess` (and `os` if unused after the move).
- Keep `BUNNY_CMD`, `_LAST`, `match()`, `run()` unchanged.

---

## Phase C — De-duplicate `SIGNAL_PATH` (parallel with Phase B)

### Step 5 — Update `src/ui/assistant_ui.py`

- Delete the local `SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")`
  near line 296.
- Add at the top (next to other `src.api.skills` imports if any, else a
  fresh import line):
  ```python
  from src.api.skills._signal import SIGNAL_PATH
  ```
- Verify `_poll_bunny_should_exit()` (lines ~299–305) still resolves the
  symbol from its new origin.

---

## Phase D — Tests (depends on B, C)

### Step 6 — Collapse `mock_subprocess` fixture

In `tests/test_skills.py` (current lines 81–84) the fixture patches
`subprocess.run` in **both** skill modules. After Phase A/B, the only
caller is `_process_utils`, so:

```python
# before
monkeypatch.setattr("src.api.skills.open_photoframe.subprocess.run", fake_run)
monkeypatch.setattr("src.api.skills.open_bunny.subprocess.run",      fake_run)

# after
monkeypatch.setattr("src.api.skills._process_utils.subprocess.run", fake_run)
```

### Step 7 — Verify constant monkeypatches still work

`TestOpenPhotoframeRun` and `TestOpenBunnyRun` use
`monkeypatch.setattr(open_photoframe, "PHOTO_PID", tmp_path / "...")`.
Because Step 3/4 keep the names imported into the skill module's
namespace (`from ._paths import PHOTO_PID`), the monkeypatch target is
unchanged. **No test code edit expected** — just rerun and confirm.

---

## Phase E — Verification (depends on D)

### Step 8 — Test suite

```
.venv/bin/pytest -q
```

Expected: **65 passed**, identical to the 012 baseline.

### Step 9 — Import smoke

```
.venv/bin/python -c "from src.api.app import app; \
    from src.api.skills import open_photoframe, open_bunny; print('ok')"
```

### Step 10 — Grep sweeps

```
grep -RIn '_pids\|_kill_all\|_alive_from_pidfile' src/api/skills/
```
Expect hits only in `_process_utils.py` (definitions) and the import
lines of the two skill modules.

```
grep -RIn 'SIGNAL_PATH\s*=\s*Path' src/
```
Expect a single hit in `src/api/skills/_signal.py`.

### Step 11 — Live verification (await user OK)

After explicit user approval, restart and re-run the four 012 smoke
curls:

```
./rabbitctl.sh restart

curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"打開相框"}'   | jq    # meta.source = local-skill, action = open_photoframe
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"切回兔兔"}'   | jq    # meta.source = local-skill, action = open_bunny
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"你好"}'       | jq    # meta.source = fallback-openai
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"幫我查台北天氣"}' | jq # meta.source = openai-websearch
```

Confirm photoframe and bunny actually launch on the device.

---

## Phase F — Wrap-up (requires user approval at each gate)

### Step 12 — Docs

- `.docs/tech-debt.md`: add a Resolved row referencing 013 for the
  helper / SIGNAL_PATH duplication (no Active rows currently match
  exactly — add under Resolved).
- `.docs/context.md`: append `013 ✅` notes.
- `PLAN.md`: add Phase 14 = 013 ✅ row.

### Step 13 — Archive plan

`git mv .docs/exec-plans/013-consolidate-skill-helpers.md \
        .docs/exec-plans/done/`

### Step 14 — Commit (await user OK)

Single commit:

```
refactor(013): consolidate skill process helpers and SIGNAL_PATH

- Extract _pids/_count/_kill_all/_kill_pidfile/_alive_from_pidfile to
  src/api/skills/_process_utils.py.
- Extract VOICE_DIR/PHOTO_PID/BUNNY_PID to src/api/skills/_paths.py.
- Replace duplicated SIGNAL_PATH literal in src/ui/assistant_ui.py with
  an import from src.api.skills._signal.
- Collapse the dual subprocess.run patch in tests/test_skills.py to a
  single patch on _process_utils.

No behaviour change. pytest 65 passed. Live curl smoke 4/4 OK.
```

### Step 15 — Push (await user OK)

`git push origin main` only after explicit user approval.

---

## Relevant files

- `src/api/skills/_paths.py` — **NEW** — three shared path constants.
- `src/api/skills/_process_utils.py` — **NEW** — five pgrep/kill helpers.
- `src/api/skills/open_photoframe.py` — replace helpers + 3 constants
  with imports; keep `PHOTO_CMD` / `PHOTO_READY` / `_LAST` / `run()`.
- `src/api/skills/open_bunny.py` — replace helpers + 3 constants with
  imports; keep `BUNNY_CMD` / `_LAST` / `run()`.
- `src/ui/assistant_ui.py` — drop local `SIGNAL_PATH`, import from
  `src.api.skills._signal`.
- `tests/test_skills.py` — collapse two `subprocess.run` patches into
  one targeting `_process_utils`.
- `.docs/tech-debt.md`, `.docs/context.md`, `PLAN.md` — Phase F docs.

## Verification summary

1. `.venv/bin/pytest -q` → 65 passed.
2. `python -c "from src.api.app import app"` exits 0.
3. Grep: helper definitions only in `_process_utils.py`; single
   `SIGNAL_PATH = Path(...)` literal in `_signal.py`.
4. Live curl after restart — four routes return correct
   `meta.source` (`local-skill` ×2 / `fallback-openai` /
   `openai-websearch`); photoframe + bunny actually launch on device.
5. `git diff --stat` ≈ +80 / −100 lines net.

## Decisions

- **Two new modules** (`_process_utils` + `_paths`) instead of one
  combined `_internal.py` — clearer responsibility boundary, smaller
  blast radius.
- **`SIGNAL_PATH` dedup included** in this plan rather than spun out
  separately — same theme ("remove skills duplication"), trivial change.
- **Skill modules re-import constants by name**
  (`from ._paths import PHOTO_PID, ...`), keeping the symbols in the
  skill module's namespace so existing
  `monkeypatch.setattr(open_photoframe, "PHOTO_PID", ...)` calls
  continue to work without test churn.
- **No commit / push / device restart** without explicit user approval
  (AGENTS.md).
