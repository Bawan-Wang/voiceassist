````markdown
# 009 — Docs / Comments Cleanup for Removing the OpenClaw Route

## Status: Planned 🟡

## Motivation

After exec-plan 006 the websearch path became the primary route for
search/weather intents and the OpenClaw subprocess path was demoted to
"fallback only". In practice the fallback now adds:

- A second slow code path (30–90s subprocess) that is rarely exercised
- A second JSON shape that has to be defended against (see 005)
- An external CLI dependency (`openclaw agent --channel telegram …`) that
  is unrelated to the rest of voiceassist's runtime
- Stale references in docs / comments that mislead anyone reading the code

We have decided to **drop the OpenClaw route entirely** (executed in 010).
This plan (009) covers **only the documentation / comment changes** that
must accompany that removal so the repo's narrative stays accurate.

No runtime code is changed by 009. Splitting the doc edits out keeps the
code-removal PR (010) small and reviewable.

---

## Pre-flight

- [ ] 010 is **not** required to be merged before 009. Either order is fine,
      but if 009 lands first the docs will (briefly) describe a path that
      still exists in code — acceptable.
- [ ] Confirm no other unmerged branch is rewriting `PLAN.md` or
      `src/api/websearch.py` (avoid conflicts).

---

## Action Items

### Step 1 — `PLAN.md`

- [ ] Line 15 (architecture block):
  - Before:
    ```
    src/api/app.py               FastAPI backend — search/weather/browse → OpenClaw agent
    ```
  - After:
    ```
    src/api/app.py               FastAPI backend — local skills + websearch (search/weather) + OpenAI fallback
    ```
- [ ] Line 27 (progress table row 3):
  - Before: `FastAPI intent routing + OpenClaw agent`
  - After:  `FastAPI intent routing + OpenAI/websearch`
- [ ] Add a new row to the progress table:
  ```
  | 12 | Drop OpenClaw fallback route (exec-plan 010) | 🔲 Planned |
  ```
- [ ] Update "Done (archived)" paragraph after 010 is merged to include 009/010.

### Step 2 — `src/bridge/voice_bridge.py`

Comments only — **no behaviour change**.

- [ ] Line 538 docstring of `generate_reply`:
  - Before: `search=True  → local /zero-assistant API (OpenClaw Agent, timeout 90s)`
  - After:  `search=True  → local /zero-assistant API (websearch path, timeout 90s)`
- [ ] Line 546 docstring of `_reply_via_api`:
  - Before: `"""POST to local /zero-assistant (OpenClaw Agent) for search/browse."""`
  - After:  `"""POST to local /zero-assistant (websearch path) for search/browse."""`

### Step 3 — `src/api/websearch.py`

- [ ] Lines 4–6 module docstring:
  - Before:
    ```
    Replaces the slow OpenClaw subprocess path for search/weather intents.
    OpenClaw remains as a fallback in `src/api/app.py` (see exec-plan 006).
    ```
  - After:
    ```
    Primary path for search/weather intents. On failure the API falls back
    to a plain OpenAI Responses call in `src/api/app.py`
    (see exec-plans 006 and 010).
    ```

### Step 4 — `.docs/architecture.md` & `.docs/api.md` (sweep)

- [ ] `grep -n -i 'openclaw' .docs/architecture.md .docs/api.md .docs/context.md`
- [ ] For every hit that describes runtime routing, either:
  - rewrite to "websearch path → OpenAI fallback", or
  - prefix with `(historical, removed in 010)` if it documents the
    decision history.
- [ ] Do **NOT** edit anything under `.docs/exec-plans/done/` — those are
      historical records.

### Step 5 — `.docs/tech-debt.md`

- [ ] Add a new entry referencing 010:
  ```
  - OpenClaw subprocess fallback removed in exec-plan 010.
    `ZERO_USE_OPENCLAW_AGENT` env var is no longer read; safe to drop
    from any deployment scripts / systemd units.
  ```

---

## Acceptance Criteria

- [ ] `grep -rni 'openclaw' src/ PLAN.md .docs/ \
      | grep -v '\.openclaw/workspace' \
      | grep -v '\.docs/exec-plans/done/'` returns **only** intentional
      historical references (e.g. the new 010 plan, the new tech-debt entry)
- [ ] `pytest` is **not** run for this plan (no code change). If you ran it
      anyway, results must match `main` exactly.
- [ ] Commit: `docs(009): drop OpenClaw references ahead of 010 removal`

---

## Rollback Plan

Pure docs change. If 010 is later abandoned, revert this commit — no runtime
impact either way.

---

## Out of Scope

- Any change to `src/api/app.py`, `tests/`, `tests/fixtures/cases.json`,
  or `tests/conftest.py`. All of those belong to 010.
- Editing files under `.docs/exec-plans/done/` (historical record).
- Removing the literal string `.openclaw` from filesystem paths
  (`VOICE_DIR`, `PHOTO_CMD`, etc.) — those are install-location paths,
  not OpenClaw runtime references.

````
