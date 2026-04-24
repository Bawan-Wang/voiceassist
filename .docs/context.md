# context.md — Current Dev Focus & Known Issues

## Current Focus

- Project layout migration complete (`src/`, `.docs/` structure in place)
- Product specs written for all core features (see `.docs/product-specs/`)
- Next: VLM model bridge (exec-plan 002), Taiwan server racing fix (exec-plan 003)

## Environment Constraints

- **Platform**: Raspberry Pi OS (ARM64)
- **Python**: 3.11 via `.venv/`
- **Audio**: PipeWire / PulseAudio — input device auto-detected or set via `RABBIT_INPUT_DEVICE`
- **TTS**: Local Piper binary — must be on `$PATH`
- **STT**: Sherpa-ONNX `sense_voice` model — model path set in `config.yaml`
- **Display**: `:0` — `DISPLAY=:0` required for PyGame UI

## Tech Debt

See `.docs/tech-debt.md` for the full list of known issues and fixes.
