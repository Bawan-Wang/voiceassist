# context.md — Current Dev Focus & Known Issues

## Current Focus

- ✅ Exec-plan 005 done — OpenClaw error responses no longer spoken to the user.
- ✅ Exec-plan 006 done — search/weather now uses OpenAI Responses API with the
  built-in `web_search` tool (3–8 s typical, vs 30–90 s on OpenClaw). OpenClaw
  remains as the fallback path; can be force-disabled with
  `VOICEASSIST_DISABLE_WEBSEARCH=1`.
- ✅ Exec-plan 007 done — voice command "打開相框 / 相簿 / 照片 / 切回兔兔" now
  routes through `src/api/skills/` registry; voice bridge gained an
  `is_local_skill()` pre-check so these phrases hit `/zero-assistant`
  instead of being streamed as chitchat. Bunny UI fades out via
  `/tmp/voiceassist_signal.json` IPC. `run_photoframe.sh` has a kivy
  preflight so silent failure is impossible.
- 🔲 Next: 008 (photoframe-side fade-in + graceful exit), then VLM bridge.

## Search/Weather Routing (post-006)

```
search intent
  │
  ├─ try src/api/websearch.run_websearch()  → OpenAI Responses + web_search tool
  │     └─ success → meta.source = "openai-websearch"
  │
  └─ on failure / disabled
        └─ OpenClaw subprocess (005-hardened)  → meta.source = "openclaw-agent"
              └─ on failure → OpenAI plain GPT-4o-mini  → meta.source = "fallback-openai"
```

## Environment Constraints

- **Platform**: Raspberry Pi OS (ARM64)
- **Python**: 3.11 via `.venv/`
- **Audio**: PipeWire / PulseAudio — input device auto-detected or set via `RABBIT_INPUT_DEVICE`
- **TTS**: Local Piper binary — must be on `$PATH`
- **STT**: Sherpa-ONNX `sense_voice` model — model path set in `config.yaml`
- **Display**: `:0` — `DISPLAY=:0` required for PyGame UI

## Known Upstream Issues

- **OpenClaw error wrapping**: when the upstream LLM (`gpt-5.3-codex` via
  github-copilot provider) hits `400 input item ID does not belong to this
  connection`, OpenClaw returns `status: "ok"`, `returncode: 0`, but
  `result.meta.stopReason: "error"` and stuffs the raw error string into
  `payloads[0].text`. Mitigated in 005 by checking `stopReason`. Now bypassed
  by 006 for the hot path — OpenClaw is only invoked as fallback.

## Tech Debt

See `.docs/tech-debt.md` for the full list of known issues and fixes.
