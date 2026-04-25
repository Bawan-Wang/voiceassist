# context.md — Current Dev Focus & Known Issues

## Current Focus

- ✅ Exec-plan 005 done — OpenClaw error responses no longer spoken back to user
  (added `meta.stopReason == "error"` and `returncode` checks; `_extract_text`
  now only walks `payloads[].text`).
- 🟡 Next: exec-plan 006 — replace OpenClaw search path with OpenAI Responses
  API + `web_search` tool (3–8s vs 30–90s); keep OpenClaw as fallback.

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
  `payloads[0].text`. Mitigated in 005 by checking `stopReason` and falling
  back to OpenAI. Real fix is exec-plan 006 (drop OpenClaw from the hot path).

## Tech Debt

See `.docs/tech-debt.md` for the full list of known issues and fixes.
