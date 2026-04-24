# context.md — Current Dev Focus & Known Issues

## Current Focus

- Migrating project layout: `api/`, `bridge/`, `ui/` → `src/api/`, `src/bridge/`, `src/ui/`
- Setting up `.docs/` structure for AI agent + human developer alignment

## Environment Constraints

- **Platform**: Raspberry Pi OS (ARM64)
- **Python**: 3.11 via `.venv/`
- **Audio**: PipeWire / PulseAudio — input device auto-detected or set via `RABBIT_INPUT_DEVICE`
- **TTS**: Local Piper binary — must be on `$PATH`
- **STT**: Sherpa-ONNX `sense_voice` model — model path set in `config.yaml`
- **Display**: `:0` — `DISPLAY=:0` required for PyGame UI

## Active Tech Debt

> Migrated from `docs/tech-debt.md` — keep this section in sync.

### LOW — `AssistRequest.language` / `source` fields unused
- **File:** `src/api/app.py`
- Both fields are accepted by the API but never read or used.

### LOW — `_should_route_without_wake()` length fallback may false-trigger
- **File:** `src/bridge/voice_bridge.py`
- `len(t) >= 8` routes any 8+ character utterance even without a wake word.

### LOW — `DEFAULT_VOICE = "verse"` never used
- **File:** `src/bridge/voice_bridge.py`
- Shadowed by `--voice shimmer` in `rabbitctl.sh`.

### LOW — `PHOTOFRAME_SCRIPT` constant unused
- **File:** `src/api/app.py`
- Defined but never referenced.

## Resolved Tech Debt

| Commit | Item |
|--------|------|
| `c16a9f8` | `BASE_DIR` in voice_bridge pointed to `bridge/` instead of repo root |
| `c16a9f8` | `open_bunny_ui()` kill pattern missing `ui/` prefix |
| `bfc6175` | openclaw `TimeoutExpired` silently fell back to OpenAI |
| `29e91ff` | openclaw stderr merged with stdout corrupted JSON |
| `be2a567` | Weather queries hardcoded city map caused wrong lookups |
