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
| `016`  | Quadruplicated voiceBridge config (~30 keys × 4 layers ≈ 90 duplicated literals: `config.yaml` + `DEFAULT_VOICEBRIDGE_CONFIG` dict + `BridgeConfig` field defaults + inline `.get(k, BridgeConfig.k)` fallbacks). Collapsed by deleting the dict layer + `_deep_merge`, removing every dataclass default (35 fields now required), and switching `build_bridge_config()` to strict `dict[k]` subscripting (`KeyError → ValueError("config.yaml missing voiceBridge.<key>")`). yaml `messageSource:` block also dropped — UI now reads `voiceBridge.state_path`. yaml is the single source of runtime truth |
| `015`  | Triplicated runtime config (17 module-level globals in `voice_bridge.py` + `DEFAULT_VOICEBRIDGE_CONFIG` in `runtime_config.py` + `voiceBridge:` block in `config.yaml`); collapsed by adding 9 new fields to `BridgeConfig`, deleting `apply_runtime_config()`, and giving `update_state()` an explicit `state_path` arg. Dead `voiceBridge.text.search_tokens` yaml block also dropped. `BridgeConfig` is now the single runtime-truth source |
| `014`  | `SEARCH_TOKENS` tuple + `is_search_intent()` were duplicated byte-for-byte in `src/api/app.py` and `src/bridge/voice_bridge.py`; consolidated into `src/api/skills/tokens.py`. Dead `_SEARCH_TOKENS` runtime-config override in `apply_runtime_config()` removed (the yaml `voiceBridge.text.search_tokens` block became a no-op and can be deleted in a future cleanup) |
| `013`  | Duplicated process helpers (`_pids`/`_count`/`_kill_all`/`_kill_pidfile`/`_alive_from_pidfile`) and `VOICE_DIR`/`PHOTO_PID`/`BUNNY_PID` constants extracted to `src/api/skills/_process_utils.py` + `_paths.py`; duplicated `SIGNAL_PATH` literal in `src/ui/assistant_ui.py` replaced with import from `src.api.skills._signal` |
| `012`  | `PHOTOFRAME_SCRIPT` constant removed alongside the deprecated 相框/兔兔 hard-coded routes |
| `c16a9f8` | `BASE_DIR` in voice_bridge pointed to `bridge/` instead of repo root → `STATE_PATH` was writing to wrong location |
| `c16a9f8` | `open_bunny_ui()` kill pattern missing `ui/` prefix |
| `bfc6175` | openclaw `TimeoutExpired` was silently falling back to OpenAI instead of returning a clear error |
| `29e91ff` | openclaw stderr merged with stdout corrupted JSON → `json.loads()` failure |
| `be2a567` | Weather queries hardcoded city map caused wrong city lookups → replaced with openclaw agent live search |
