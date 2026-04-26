````markdown
# 010 — Remove the OpenClaw Subprocess Route from `/zero-assistant`

## Status: Planned 🟡

## Motivation

Since 006 the OpenClaw `agent` subprocess has only been a fallback for the
websearch path. In practice it is:

- **Slow** — 30–90s per call vs ~5s for the websearch path
- **Fragile** — multiple JSON shapes and `meta.stopReason="error"` traps
  (see exec-plan 005)
- **Coupled to an external CLI** (`openclaw agent --channel telegram …`)
  that is unrelated to voiceassist's core stack
- **Rarely exercised** — websearch covers all production search/weather
  traffic; the only time openclaw runs is when websearch fails, where the
  plain OpenAI fallback is a strictly simpler and faster behaviour

This plan removes the OpenClaw subprocess block from `src/api/app.py` and
all dependent test scaffolding. After 010, the request flow becomes:

```
POST /zero-assistant
   → local skills (open_photoframe / open_bunny / …)
   → legacy hard-coded 相框/兔兔 routes (kept for safety, see 007 TODO)
   → websearch path                  (search / weather intents only)
   → plain OpenAI Responses fallback (everything else, and websearch failures)
```

009 (docs cleanup) is sibling to this plan; either order is fine.

---

## Pre-flight

- [ ] Confirm 006 / 007 have shipped (`git log --oneline | grep -E '006|007'`)
- [ ] Confirm no live deployment depends on `ZERO_USE_OPENCLAW_AGENT=…`
      (`grep -rni ZERO_USE_OPENCLAW_AGENT ~/`)
- [ ] Snapshot baseline tests:
      ```bash
      cd /home/jh-pi/.openclaw/workspace/voiceassist
      .venv/bin/pytest -q | tee /tmp/voiceassist-pre-010.log
      ```

---

## Action Items

### Step 1 — Remove OpenClaw block from `src/api/app.py`

- [ ] Delete line 33:
      ```python
      USE_OPENCLAW_AGENT = os.environ.get("ZERO_USE_OPENCLAW_AGENT", "1") == "1"
      ```
- [ ] In `zero_assistant()` (~line 200):
  - [ ] Drop the now-unused locals `agent_timeout` / `cli_timeout`
        (lines ~209–212)
  - [ ] Rewrite the comment block at lines 203–215 to describe the new
        two-step path: "websearch for search intents, plain OpenAI for
        everything else (including websearch failures)"
  - [ ] On line 227 change the fallback log message:
        ```python
        print(f"[api] websearch failed: {exc}; falling back to openai", flush=True)
        ```
- [ ] Delete the entire OpenClaw subprocess block (`if USE_OPENCLAW_AGENT:`
      through the trailing `except Exception: pass`, ~lines 229–287).
      That removes:
  - The inner `_extract_text` helper
  - `subprocess.run(["openclaw", "agent", …])`
  - `_json.loads(out)` + `meta.stopReason` handling
  - The `subprocess.TimeoutExpired` "請等一下再問我一次" branch
- [ ] Verify the file still imports cleanly and `subprocess` / `json`
      imports are still used elsewhere; if not, remove them.
- [ ] Keep lines 25 / 30 (`VOICE_DIR`, `PHOTO_CMD`) untouched — those are
      filesystem paths that just happen to live under `~/.openclaw/`.

### Step 2 — Trim `tests/conftest.py`

- [ ] Remove `_make_openclaw_result()` helper (lines ~19–26).
- [ ] Remove the `mock_openclaw` fixture (lines ~44–49).
- [ ] In `client` and `client_with_websearch` fixture signatures, drop
      the `mock_openclaw` parameter:
      ```python
      def client(mock_openai, monkeypatch):
      def client_with_websearch(mock_openai, monkeypatch):
      ```
- [ ] Update the module docstring (line 6) — remove the
      `subprocess.run → mocks openclaw agent responses` bullet.

### Step 3 — Rewrite `tests/test_api.py`

- [ ] Delete the entire `class TestOpenclawRouting` block (~lines 90–175,
      7 tests). It exercises code that no longer exists.
- [ ] In `class TestWebsearchRouting`:
  - [ ] `test_websearch_failure_falls_back_to_openclaw` →
        rename to `test_websearch_failure_falls_back_to_openai`; change the
        final assertion to `meta["source"] == "fallback-openai"`.
  - [ ] `test_chitchat_does_not_use_websearch`: change the trailing
        assertion from `"openclaw-agent"` to `"fallback-openai"`.
  - [ ] `test_disable_env_skips_websearch`: add a new assertion
        `assert r.json()["meta"]["source"] == "fallback-openai"`.
- [ ] Add a small new test (e.g. just before `TestWebsearchRouting`):
      ```python
      class TestGeneralQA:
          def test_chitchat_uses_openai_fallback(self, client):
              r = client.post("/zero-assistant", json={"text": "你好"})
              assert r.status_code == 200
              assert r.json()["meta"]["source"] == "fallback-openai"
      ```
- [ ] Update the file header docstring — drop the mention of mocking
      `openclaw`.

### Step 4 — Update `tests/fixtures/cases.json`

- [ ] For the four entries currently set to `"expected_source": "openclaw-agent"`:
  | id                  | new `expected_source` |
  | ------------------- | --------------------- |
  | `weather_kaohsiung` | `openai-websearch`    |
  | `weather_generic`   | `openai-websearch`    |
  | `search_news`       | `openai-websearch`    |
  | `general_qa`        | `fallback-openai`     |
- [ ] Adjust each `description` field to drop the word "openclaw-agent".
- [ ] Leave `open_photoframe` / `open_bunny` / `empty_input` unchanged
      (the existing `"local-command"` mismatch with the actual
      `"local-skill"` source is tracked separately in `tech-debt.md`).

### Step 5 — Verify

- [ ] `.venv/bin/pytest -q` — must be all green.
- [ ] Diff the test summary against `/tmp/voiceassist-pre-010.log`. The
      delta should be exactly:
  - 7 tests removed (`TestOpenclawRouting::*`)
  - 1 test renamed (`test_websearch_failure_falls_back_to_openclaw`
    → `…_openai`)
  - 1 test added (`TestGeneralQA::test_chitchat_uses_openai_fallback`)
- [ ] Manual smoke test on the device:
      ```bash
      curl -s localhost:8765/zero-assistant \
        -H 'Content-Type: application/json' \
        -d '{"text":"你好"}' | jq
      # → expect meta.source == "fallback-openai"

      curl -s localhost:8765/zero-assistant \
        -H 'Content-Type: application/json' \
        -d '{"text":"幫我查新北今天天氣"}' | jq
      # → expect meta.source == "openai-websearch"
      ```
- [ ] `grep -n 'openclaw\|OpenClaw' src/ tests/ -r` should now only match:
  - install-location paths under `.openclaw/workspace/...`
  - the new 009 / 010 plan files (if they live in `.docs/`, not `src/`)

### Step 6 — Commit

- [ ] `git add -A`
- [ ] Commit: `feat(010): remove OpenClaw subprocess route from /zero-assistant`
- [ ] Move `009-docs-drop-openclaw-route.md` and
      `010-remove-openclaw-route.md` to
      `.docs/exec-plans/done/` once verified on device.
- [ ] Update `PLAN.md` "Done (archived)" paragraph accordingly (this last
      bullet may belong to 009 instead, whichever lands second).

---

## Acceptance Criteria

- [ ] `pytest` green, with the test delta described in Step 5.
- [ ] No reference to `openclaw agent`, `USE_OPENCLAW_AGENT`,
      `openclaw-agent-timeout`, or the `subprocess.run([... "openclaw" ...])`
      call remains in `src/` or `tests/`.
- [ ] `/zero-assistant` returns `meta.source == "fallback-openai"` for
      chitchat and `"openai-websearch"` for search/weather (verified on
      device).
- [ ] Latency for chitchat (`你好`) is ≤ what it was on `main`
      (no fallback subprocess in the path → should usually be faster).
- [ ] No regression in local-skill paths (`打開相框`, `切回兔兔`).

---

## Rollback Plan

If 010 breaks production:

1. `git revert <commit-of-010>` — the change is a single commit covering
   `src/api/app.py`, `tests/conftest.py`, `tests/test_api.py`,
   `tests/fixtures/cases.json`. Revert is mechanical.
2. Re-deploy. The OpenClaw subprocess path returns immediately because the
   `openclaw` CLI is still installed at `~/.npm-global/bin/openclaw`.
3. Re-open this plan with the failing scenario captured before retrying.

A softer in-place rollback (without revert) is **not** offered: removing
`USE_OPENCLAW_AGENT` means there is no env-var kill-switch left after 010.
That is intentional — the kill-switch was carrying its own maintenance cost.

---

## Out of Scope

- Changing the chitchat → `gpt-4o-mini` model choice or system prompt.
- Changing the websearch path itself (still owned by 006).
- Removing the legacy hard-coded 相框/兔兔 routes — that is the 007 TODO.
- Uninstalling the `openclaw` CLI from the device — harmless to leave.
- Editing `.docs/architecture.md` / `PLAN.md` narrative text — handled by 009.

---

## Dependencies & Risks

- **Depends on 006** (websearch path must already be the primary search route).
- **Risk**: a user query that previously needed OpenClaw's tool-calling
  ability (e.g. multi-step browse) now degrades to a plain `gpt-4o-mini`
  reply with no tools. Mitigation: in practice such queries are already
  routed through websearch; the OpenClaw path was effectively dead code.
- **Risk**: hidden callers patching `src.api.app.subprocess.run` for
  openclaw scenarios will break. Mitigation: Step 3 already removes all
  in-repo callers; external callers shouldn't exist.

````
