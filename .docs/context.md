# context.md — Current Dev Focus & Known Issues

## Current Focus

- ✅ Exec-plan 018B done — `.github/workflows/hardware-smoke.yml` now adds a
  manual, non-blocking Raspberry Pi hardware smoke workflow on the dedicated
  runner labels `self-hosted`, `linux`, `ARM64`, `voiceassist-pi`. It
  serializes runs with concurrency, executes against the canonical checkout at
  `/home/jh-pi/.openclaw/workspace/voiceassist`, validates config load plus
  `rabbitctl.sh` start / status / stop, and uploads `/tmp` logs on failure.
  Local on-device smoke passed on 2026-05-08: config loaded, all three managed
  processes came up, expected logs were created, and teardown returned to a
  clean stopped state.
- ✅ Exec-plan 018A done — GitHub-hosted workflows now exist under
  `.github/workflows/`: `ci.yml` installs `requirements.txt` +
  `requirements-dev.txt`, runs `pytest -q`, then runs informational
  `pip-audit` and `gitleaks`; `codeql.yml` adds hosted Python CodeQL
  analysis on pull requests and pushes to `main`. This remains the portable
  PR baseline; 018B now covers the manual Pi-only smoke path separately.
- ✅ Exec-plan 005 done — OpenClaw error responses no longer spoken to the user.
- ✅ Exec-plan 006 done — search/weather now uses OpenAI Responses API with the
  built-in `web_search` tool (3–8 s typical, vs 30–90 s on OpenClaw). On
  failure the API falls straight through to a plain OpenAI Responses call.
  Can still be force-disabled with `VOICEASSIST_DISABLE_WEBSEARCH=1`.
- ✅ Exec-plan 007 done & live-verified — voice command "打開相框 / 相簿 /
  照片 / 切回兔兔" now routes through `src/api/skills/` registry; voice
  bridge gained an `is_local_skill()` pre-check so these phrases hit
  `/zero-assistant` instead of being streamed as chitchat. Bunny UI fades
  out via `/tmp/voiceassist_signal.json` IPC. `run_photoframe.sh` has a
  kivy preflight so silent failure is impossible. Live testing surfaced
  one bug (fix `e38e3f3`): the fuzzy wake-word stripper was eating the
  trailing "兔兔" in "兔兔助理切回兔兔" because variant `兔兔兔` fuzzy-
  matches `回兔兔`. Voice bridge now falls back to checking the raw
  transcript when the stripped command misses local-skill tokens.
- ✅ Exec-plan 008 done — photoframe (`~/workspace/photoframe/main.py`)
  now fades in over 0.4s on launch and exits gracefully via
  `/tmp/voiceassist_signal.json` (`photoframe_should_exit=true`) instead
  of being kill -9'd. Photoframe also touches `/tmp/photoframe.ready`
  so `open_photoframe` can verify a real successful launch (1.5s
  timeout). Backup at `~/workspace/photoframe.bak.20260425`.
- ✅ Exec-plan 009 done — docs swept clean of OpenClaw fallback references
  ahead of the runtime removal.
- ✅ Exec-plan 010 done — OpenClaw subprocess route removed from
  `src/api/app.py`; `/zero-assistant` is now strictly websearch →
  fallback-openai. `ZERO_USE_OPENCLAW_AGENT` env var no longer read.
- ✅ Exec-plan 011 done — stale `VLM model bridge` and `Taiwan server
  racing fix` rows removed from `PLAN.md` Overall Progress table.
- ✅ Exec-plan 012 done — deprecated hard-coded 相框/兔兔 routes and the
  legacy `open_photoframe()` / `open_bunny_ui()` helpers removed from
  `src/api/app.py` (~200 lines). `match_skill()` is now the only
  local-skill dispatcher. `subprocess` and `time` imports also dropped.

## Search/Weather Routing (post-006, post-010)

```
search intent
  │
  ├─ try src/api/websearch.run_websearch()  → OpenAI Responses + web_search tool
  │     └─ success → meta.source = "openai-websearch"
  │
  └─ on failure / disabled
        └─ plain OpenAI GPT-4o-mini Responses  → meta.source = "fallback-openai"
```

## Environment Constraints

- **Platform**: Raspberry Pi OS (ARM64)
- **Python**: 3.11 via `.venv/`
- **Audio**: PipeWire / PulseAudio — input device auto-detected or set via `RABBIT_INPUT_DEVICE`
- **TTS**: Piper models are loaded by the in-repo Python provider configured in `config.yaml`; no standalone `piper` binary on `$PATH` is required
- **STT**: Sherpa-ONNX `sense_voice` model — model path set in `config.yaml`
- **Display**: `:0` — `DISPLAY=:0` required for PyGame UI
- **Hardware smoke runner**: dedicated Pi checkout must stay at `/home/jh-pi/.openclaw/workspace/voiceassist` with audio/display available and no competing local activity during manual smoke runs

## Known Upstream Issues

- **OpenClaw error wrapping** (historical, removed in 010): when the upstream
  LLM (`gpt-5.3-codex` via github-copilot provider) hit
  `400 input item ID does not belong to this connection`, OpenClaw returned
  `status: "ok"`, `returncode: 0`, but `result.meta.stopReason: "error"` and
  stuffed the raw error string into `payloads[0].text`. Mitigated in 005,
  bypassed by 006 for the hot path, and removed entirely in 010 when the
  OpenClaw subprocess route was deleted from `src/api/app.py`.

## Tech Debt

See `.docs/tech-debt.md` for the full list of known issues and fixes.

## Recent Refactors

- **013** ✅ — Skill process helpers (`_pids` / `_count` / `_kill_all` /
  `_kill_pidfile` / `_alive_from_pidfile`) and shared path constants
  (`VOICE_DIR` / `PHOTO_PID` / `BUNNY_PID`) extracted from
  `open_photoframe.py` + `open_bunny.py` into
  `src/api/skills/_process_utils.py` + `_paths.py`. The duplicated
  `SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")` literal in
  `src/ui/assistant_ui.py` now imports from
  `src.api.skills._signal`. Net −95 lines in tracked files; pytest 65
  passed; live curl 4/4 OK.
- **014** ✅ — `SEARCH_TOKENS` tuple + `is_search_intent()` consolidated
  into `src/api/skills/tokens.py` (the dependency-free token module).
  `src/api/app.py` and `src/bridge/voice_bridge.py` now import the
  canonical helper instead of carrying byte-identical local copies.
  Dead `_SEARCH_TOKENS` runtime-config override in
  `apply_runtime_config()` removed (the yaml block was a no-op carbon
  copy of the defaults). pytest 72 passed; import smoke confirms the
  bridge symbol resolves to the canonical function object.
- **015** ✅ — collapsed module-level config globals into
  `BridgeConfig`. `voice_bridge.py` lost 17 module-level constants and
  the 35-line `apply_runtime_config()` global-mutator; `BridgeConfig`
  gained 9 new fields (`state_path`, `silero_model_path/url`,
  `llm_model`, `llm_system_prompt`, `spoken_reply_prompt`,
  `trim_chars`, `sentence_endings`, `stream_chunk_chars`).
  `update_state()` now takes `state_path` as the first arg.
  `build_arg_parser()` receives `default_playback`/`default_wake` from
  `main()`, so the argparse layer no longer touches L1 globals.
  Dead `voiceBridge.text.search_tokens` yaml block (014 leftover)
  dropped from both `config.yaml` and `runtime_config.DEFAULT_VOICEBRIDGE_CONFIG`.
  pytest 74 passed; live curl + mic sanity OK.
- **016** ✅ — made `config.yaml` the single source of runtime truth.
  Deleted `DEFAULT_VOICEBRIDGE_CONFIG` (~95-line dict) and `_deep_merge`
  from `runtime_config.py`; `load_app_config()` now strict-loads
  (file + top-level `voiceBridge` key required). `BridgeConfig` lost
  every field default (35 required fields; bare `BridgeConfig()` now
  raises `TypeError` by design). `build_bridge_config()` uses direct
  `dict[k]` subscripting wrapped in a single try/except that converts
  `KeyError → ValueError("config.yaml missing voiceBridge key: '<k>'")`.
  `messageSource:` yaml block dropped — `assistant_ui.py` now reads
  `voiceBridge.state_path`. ~90 duplicated literals across 4 layers
  collapsed to 1. pytest 76 passed (+2 new strict-mode tests); live
  restart confirmed 3 PIDs up + voice_bridge `Ready` log clean.
- **017** ✅ — normalized the dependency manifests to match direct runtime
  imports and entrypoints. `requirements.txt` now explicitly declares
  `fastapi`, `pydantic`, `requests`, and `uvicorn` alongside the existing
  audio / model / OpenAI packages; `README.md` now documents installing
  `requirements-dev.txt` on top of runtime requirements for local tests
  and CI. Verified with `.venv/bin/pytest -q` = 76 passed and a fresh
  throwaway venv install + pytest = 76 passed.
