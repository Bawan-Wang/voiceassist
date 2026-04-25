# 005 — Fix Search Query Returning Raw Error Messages

## Status: Active 🔴

## Symptoms

When user asks search/weather queries (e.g. "幫我查今天新北市的天氣"), the assistant speaks a technical error string instead of a helpful reply:

```
[voice_bridge] API reply: 400 input item ID does not belong to this connection
[voice_bridge] Search speech rewrite: 出現了錯誤，表示這個項目的 ID 與當前連接不符。
[voice_bridge] Speaking: 出現了錯誤，表示這個項目的 ID 與當前連接不符
```

---

## Root Cause Analysis

### Bug 1 (HIGH) — `_extract_text()` swallows OpenClaw error responses

**File:** `src/api/app.py`

When OpenClaw returns an error JSON (e.g. 400 from its upstream API), `_extract_text()` recurses through ALL dict/list values and returns the first non-empty string it finds — which is the raw error message string.

```python
if isinstance(node, dict):
    for v in node.values():
        got = _extract_text(v)  # too aggressive — finds error strings
        if got:
            return got
```

OpenClaw returns something like:
```json
{ "error": "400 input item ID does not belong to this connection" }
```

`_extract_text` extracts `"400 input item ID does not belong to this connection"` and returns it as `reply_text`. The voice bridge then speaks this error verbatim to the user, then tries to "rewrite for speech" which makes it sound even more bizarre.

**Fix:** Guard `_extract_text` to only accept text from known-good payload paths (`payloads[].text`), and check `proc.returncode == 0` before trusting the output.

---

### Bug 2 (LOW) — `app.py` has stale `ui/assistant_ui.py` paths

**File:** `src/api/app.py`

After the `src/` restructure, `BUNNY_CMD` and kill patterns in `open_bunny_ui()` still use the old path:

```python
BUNNY_CMD = f"... .venv/bin/python ui/assistant_ui.py ..."   # ← old
_kill_all("python ui/assistant_ui.py")                       # ← old
```

Should be `src/ui/assistant_ui.py`. Bunny UI re-launch via voice command will fail silently.

---

## Action Items

### Bug 1 — Fix `_extract_text` and openclaw response validation

- [ ] In `app.py`, add `proc.returncode` check — if non-zero, skip to fallback:
  ```python
  if proc.returncode != 0:
      raise RuntimeError(f"openclaw non-zero exit {proc.returncode}; stderr={proc.stderr[:200]}")
  ```
- [ ] Simplify `_extract_text` to only walk `payloads[].text` path, not arbitrary dict recursion:
  ```python
  def _extract_text(node):
      # Only trust payloads[].text
      if isinstance(node, dict):
          payloads = (
              node.get("result", {}).get("payloads")
              if isinstance(node.get("result"), dict)
              else node.get("payloads")
          )
          if isinstance(payloads, list):
              for p in payloads:
                  if isinstance(p, dict) and isinstance(p.get("text"), str) and p.get("text").strip():
                      return p.get("text").strip()
      return ""
  ```
- [ ] Add test case in `tests/test_api.py`: OpenClaw returns error JSON → should fall through to OpenAI, not speak error
- [ ] Run `pytest tests/ -v` — 22/22 must pass

### Bug 2 — Fix stale paths in `app.py`

- [ ] Update `BUNNY_CMD`:
  ```python
  BUNNY_CMD = f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python src/ui/assistant_ui.py >/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
  ```
- [ ] Update `_kill_all` calls in `open_bunny_ui()`:
  ```python
  _kill_all("python src/ui/assistant_ui.py")
  ```

---

## Acceptance Criteria

- [ ] Saying "幫我查新北市天氣" → assistant speaks actual weather info (not an error string)
- [ ] If OpenClaw truly fails → assistant speaks friendly fallback: "抱歉，這個問題我查比較久，請你等一下再問我一次。"
- [ ] Saying "切回兔兔" → bunny UI launches correctly via `open_bunny_ui()`
- [ ] `pytest tests/ -v` all pass
- [ ] Commit: `fix(005): extract clean reply from openclaw, fix stale ui paths in app.py`
