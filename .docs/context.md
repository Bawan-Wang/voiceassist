# context.md — Current Dev Focus & Known Issues

## Current Focus

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
- **TTS**: Local Piper binary — must be on `$PATH`
- **STT**: Sherpa-ONNX `sense_voice` model — model path set in `config.yaml`
- **Display**: `:0` — `DISPLAY=:0` required for PyGame UI

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
