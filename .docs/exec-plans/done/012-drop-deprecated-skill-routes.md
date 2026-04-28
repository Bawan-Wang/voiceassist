# 012 — Drop Deprecated Hard-Coded Skill Routes from `src/api/app.py`

## Status: Planned 🟡

## Motivation

Exec-plan 007 introduced `src/api/skills/` as the canonical local-skill
dispatcher (`match_skill(text).run()`). For safety, the previous
hard-coded `相框` / `兔兔` routes and their helper functions were left in
`src/api/app.py` with the comment:

```python
# ── Deprecated hard-coded routes (TODO(007): remove after live verify) ──
```

007 has since been live-verified (commit `ef5dcfb` — "007 done &
live-verified; archive plan to done/"), so the legacy block is
unreachable in normal flow (skills always match first) and now exists
purely as dead code. The audit performed after 011 also flagged this as
the highest-impact piece of redundancy in the repo (~150 lines).

This plan deletes the deprecated routes, the legacy `open_photoframe()` /
`open_bunny_ui()` functions, and every helper / constant that only
existed to serve them. After 012, `zero_assistant()` has a single,
linear decision tree:

```
local-skill → openai-websearch → fallback-openai
```

Helper / constant **consolidation** across `app.py` and the two skill
modules is intentionally out of scope — that is exec-plan 013.

---

## Pre-flight

- [ ] Confirm 010 + 011 have shipped:
      `git log --oneline | grep -E '010|011'`
- [ ] Snapshot baseline tests:
      ```bash
      cd /home/jh-pi/.openclaw/workspace/voiceassist
      .venv/bin/pytest -q | tee /tmp/voiceassist-pre-012.log
      ```
      Expected: `65 passed`.
- [ ] Confirm `src/api/skills/` is the canonical dispatcher
      (`grep -n match_skill src/api/app.py` should show the import + call
      inside `zero_assistant()`).

---

## Action Items

### Step 1 — Delete the deprecated hard-coded routes

- [ ] In `src/api/app.py`, inside `zero_assistant()`, delete the entire
      `# ── Deprecated hard-coded routes (TODO(007): remove after live
      verify) ──` block (~lines 194–200), including:
  - `tl = text.lower()`
  - the `("打開" in text or "開啟" in text) and ("相框" in text or "photoframe" in tl)` branch
  - the `("打開" in text or "開啟" in text or "切回" in text) and ("兔兔" in text or "bunny" in tl)` branch
- [ ] After this step, the function should fall straight from the
      `match_skill(...)` block into the `# LLM path` comment.

### Step 2 — Delete the legacy module-level functions

- [ ] Delete `def open_photoframe()` (~lines 110–139). Only the deleted
      Step 1 routes called it.
- [ ] Delete `def open_bunny_ui()` (~lines 141–165). Same reason.

### Step 3 — Delete helpers and state that only Steps 1–2 used

- [ ] Delete `_LAST_ACTION = {"name": "", "ts": 0.0}` (line 33).
- [ ] Delete `def _debounce(action, seconds=2.5)` (~lines 49–55).
- [ ] Delete `def _pids(pattern)` (~lines 58–69).
- [ ] Delete `def _count(pattern)` (~lines 72–73).
- [ ] Delete `def _kill_all(pattern)` (~lines 76–81).
- [ ] Delete `def _kill_pidfile(path)` (~lines 84–95).
- [ ] Delete `def _alive_from_pidfile(path)` (~lines 98–106).
- [ ] (Each of these has an identical copy in
      `src/api/skills/open_photoframe.py` and
      `src/api/skills/open_bunny.py`. De-duplication of those copies is
      013, not this plan.)

### Step 4 — Delete now-orphaned module-level constants

- [ ] Delete `PHOTOFRAME_SCRIPT = …` (line 26) — never read anywhere.
- [ ] Delete `BUNNY_PID = …` (line 27) — only used by deleted helpers.
- [ ] Delete `PHOTO_PID = …` (line 28) — only used by deleted helpers.
- [ ] Delete `BUNNY_CMD = …` (line 29) — only used by deleted helpers.
- [ ] Delete `PHOTO_CMD = …` (line 30) — only used by deleted helpers.
- [ ] Re-check `VOICE_DIR = Path(...)` (line 25): it was only consumed
      by `BUNNY_CMD` / `PHOTO_CMD`. If `grep -n VOICE_DIR src/api/app.py`
      now returns no other references, delete it too. Otherwise leave it.

### Step 5 — Trim now-unused imports

- [ ] At the top of `src/api/app.py`, remove `import subprocess` and
      `import time`. Both were only used by the deleted helpers /
      `_debounce`. (Keep `os`, `re`, `Path` — `resolve_openai_key()`
      still needs them.)
- [ ] Verify with `python -c "from src.api.app import app; print('ok')"`.
- [ ] If pytest later fails with an `ImportError`, add the missing
      import back and proceed.

### Step 6 — Verify tests still pass

- [ ] `tests/test_api.py::TestLocalCommands` already patches
      `src.api.skills.open_photoframe.run` /
      `src.api.skills.open_bunny.run`, so it exercises the canonical
      `match_skill` path. No test code change required.
- [ ] Run: `.venv/bin/pytest -q`
- [ ] Expected: `65 passed` (delta vs `/tmp/voiceassist-pre-012.log`
      should be exactly zero — no tests added, removed, or renamed).

### Step 7 — Sweep for dangling references

- [ ] `grep -n 'PHOTOFRAME_SCRIPT\|_LAST_ACTION\|_debounce\|_pids\|_kill_pidfile\|open_photoframe\|open_bunny_ui' src/api/app.py`
  - Allowed: `from .skills import match_skill` and any `match_skill`
    return-value usage.
  - Disallowed: any `def open_photoframe`, `def open_bunny_ui`, or
    standalone helper definition in `app.py`.
- [ ] `grep -n 'BUNNY_PID\|PHOTO_PID\|BUNNY_CMD\|PHOTO_CMD\|PHOTOFRAME_SCRIPT' src/api/app.py`
      should return nothing.

### Step 8 — Update tech-debt tracker

- [ ] In `.docs/tech-debt.md`, move
      `LOW — PHOTOFRAME_SCRIPT constant unused`
      from **Active** to **Resolved** with the 012 commit hash.
- [ ] Leave the other Active items
      (`AssistRequest.language/source`,
       `_should_route_without_wake length fallback`,
       `DEFAULT_VOICE = "verse"`)
      untouched — they are out of scope for this plan.

### Step 9 — Commit and archive

- [ ] `git add -A`
- [ ] Commit:
      ```
      refactor(012): drop deprecated hard-coded skill routes from app.py

      007's match_skill() dispatcher has been live-verified since ef5dcfb;
      the parallel hard-coded 相框/兔兔 block was unreachable dead code.
      Remove ~150 lines: the routes themselves, the legacy
      open_photoframe()/open_bunny_ui() functions, _debounce + _LAST_ACTION,
      the five process-control helpers, and the orphaned
      PHOTOFRAME_SCRIPT/BUNNY_PID/PHOTO_PID/BUNNY_CMD/PHOTO_CMD constants
      they fed. Drop now-unused subprocess and time imports.

      Helper / constant consolidation across app.py and the two skill
      modules is deferred to exec-plan 013.

      Tests: 65 passed (coverage delta = 0; no tests added or removed).
      ```
- [ ] Move `.docs/exec-plans/012-drop-deprecated-skill-routes.md` to
      `.docs/exec-plans/done/` once verified on device (Step 10).
- [ ] Update `PLAN.md` Done (archived) paragraph to include 012.

### Step 10 — Live verification on device

- [ ] Restart services (**requires explicit user approval**):
      `./rabbitctl.sh restart`
- [ ] Voice path: say `兔兔助理 打開相框` → photoframe appears, bunny
      fades out. Say `兔兔助理 切回兔兔` → bunny returns, photoframe
      exits. Check `/tmp/assistant_bridge.log` for
      `meta.source = "local-skill"`.
- [ ] HTTP path:
      ```bash
      curl -s localhost:8765/zero-assistant -H 'Content-Type: application/json' \
        -d '{"text":"打開相框"}' | jq
      # expect meta.source = "local-skill", meta.action = "open_photoframe"

      curl -s localhost:8765/zero-assistant -H 'Content-Type: application/json' \
        -d '{"text":"你好"}' | jq
      # expect meta.source = "fallback-openai"

      curl -s localhost:8765/zero-assistant -H 'Content-Type: application/json' \
        -d '{"text":"幫我查台北天氣"}' | jq
      # expect meta.source = "openai-websearch"
      ```

---

## Acceptance Criteria

- [ ] `pytest` shows `65 passed`, identical to baseline.
- [ ] `src/api/app.py` no longer defines `open_photoframe()`,
      `open_bunny_ui()`, `_debounce()`, `_LAST_ACTION`, `_pids`,
      `_count`, `_kill_all`, `_kill_pidfile`, `_alive_from_pidfile`,
      `PHOTOFRAME_SCRIPT`, `BUNNY_PID`, `PHOTO_PID`, `BUNNY_CMD`,
      or `PHOTO_CMD`.
- [ ] `import subprocess` and `import time` are gone from `app.py`
      (unless pytest forced one back).
- [ ] Live device verification (Step 10) passes for all three meta.source
      categories.
- [ ] `.docs/tech-debt.md` `PHOTOFRAME_SCRIPT` row moved to Resolved with
      the 012 commit hash.

---

## Rollback Plan

Single mechanical commit. If 012 breaks production:

1. `git revert <commit-of-012>` — restores all deleted helpers, legacy
   functions, and the deprecated routes verbatim.
2. Re-deploy / restart. Behaviour returns to pre-012 immediately because
   the canonical `match_skill` path was untouched and was already
   handling 100% of live traffic.
3. Re-open this plan with the failing scenario captured.

---

## Out of Scope

- **013**: consolidating duplicated `_pids` / `_count` / `_kill_all` /
  `_kill_pidfile` / `_alive_from_pidfile` helpers and PID/CMD constants
  across `app.py` and the two skill modules into shared modules
  (`skills/_process_utils.py`, `skills/_constants.py`). This plan only
  removes the `app.py` copies as collateral; the duplicate copies in
  `skills/open_photoframe.py` and `skills/open_bunny.py` stay until 013.
- **014**: deduplicating the `SEARCH_TOKENS` list shared between
  `app.py` and `voice_bridge.py`.
- `AssistRequest.language` / `AssistRequest.source` field cleanup — that
  is an API contract change and belongs in a separate plan.
- `_should_route_without_wake` length-fallback fix and
  `DEFAULT_VOICE = "verse"` typo — both live in `voice_bridge.py` and
  are unrelated to the `app.py` cleanup; leave in `tech-debt.md` for a
  future plan.
- Uninstalling the `openclaw` CLI from the device — handled (or
  deliberately not handled) by 010.

---

## Dependencies & Risks

- **Depends on 007**: requires `src/api/skills/match_skill` to be the
  canonical dispatcher. ✅ shipped in `4ff4b7f` and live-verified in
  `ef5dcfb`.
- **Risk**: a previously-untracked caller imports `open_photoframe` /
  `open_bunny_ui` directly from `src.api.app`. Mitigation: `grep -rn
  'from src.api.app import\|app\.open_photoframe\|app\.open_bunny_ui'`
  across the workspace before commit; the in-repo answer is "no
  callers".
- **Risk**: a test patched `src.api.app._kill_all` (or similar helper)
  rather than the skill-level copy. Mitigation: pytest in Step 6 will
  surface this immediately.
- **Risk**: subprocess/time import removal breaks an indirect user.
  Mitigation: explicitly handled by Step 5 — re-add on pytest failure.
