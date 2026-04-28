# Tech Debt Tracker

Items that are known issues or improvements deferred for later.
When fixing an item, move it to the **Resolved** section with the commit hash.

---

## Active

### LOW — `AssistRequest.language` / `source` fields unused
- **File:** `src/api/app.py` — `AssistRequest` model
- **Issue:** Both fields are accepted by the API but never read or used anywhere.
- **Fix:** Either remove them or wire them up to control routing behaviour.

### LOW — `_should_route_without_wake()` length fallback may false-trigger
- **File:** `src/bridge/voice_bridge.py`
- **Issue:** `len(t) >= 8` routes any 8+ character utterance even without a wake word or command keyword. Background noise transcribed to 8+ characters will trigger a reply.
- **Fix:** Remove the length fallback, rely only on explicit command tokens.

### LOW — `DEFAULT_VOICE = "verse"` never used
- **File:** `src/bridge/voice_bridge.py`
- **Issue:** The default voice is defined as `"verse"` but `rabbitctl.sh` always passes `--voice shimmer`, shadowing the default.
- **Fix:** Change `DEFAULT_VOICE` to `"shimmer"` to match actual behaviour.

### INFO — OpenClaw subprocess fallback removed in exec-plan 010
- **Files:** `src/api/app.py`, `tests/conftest.py`, `tests/test_api.py`, `tests/fixtures/cases.json`
- **Note:** The `ZERO_USE_OPENCLAW_AGENT` env var is no longer read; safe to drop from any deployment scripts / systemd units. The `openclaw` CLI itself can stay installed — it is harmless once unreferenced.

---

## Resolved

| Commit | Item |
|--------|------|
| `013`  | Duplicated process helpers (`_pids`/`_count`/`_kill_all`/`_kill_pidfile`/`_alive_from_pidfile`) and `VOICE_DIR`/`PHOTO_PID`/`BUNNY_PID` constants extracted to `src/api/skills/_process_utils.py` + `_paths.py`; duplicated `SIGNAL_PATH` literal in `src/ui/assistant_ui.py` replaced with import from `src.api.skills._signal` |
| `012`  | `PHOTOFRAME_SCRIPT` constant removed alongside the deprecated 相框/兔兔 hard-coded routes |
| `c16a9f8` | `BASE_DIR` in voice_bridge pointed to `bridge/` instead of repo root → `STATE_PATH` was writing to wrong location |
| `c16a9f8` | `open_bunny_ui()` kill pattern missing `ui/` prefix |
| `bfc6175` | openclaw `TimeoutExpired` was silently falling back to OpenAI instead of returning a clear error |
| `29e91ff` | openclaw stderr merged with stdout corrupted JSON → `json.loads()` failure |
| `be2a567` | Weather queries hardcoded city map caused wrong city lookups → replaced with openclaw agent live search |
