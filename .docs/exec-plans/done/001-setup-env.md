# 001 — Setup Environment

## Status: Done ✅

## Goal
Bootstrap the voiceassist development environment on Raspberry Pi.

## Steps Completed
- [x] Create `.venv/` with Python 3.11
- [x] Install `requirements.txt` and `requirements-dev.txt`
- [x] Configure `config.yaml` with audio devices, STT/TTS model paths
- [x] Verify `rabbitctl.sh start` launches all three services
- [x] Verify `pytest tests/ -v` passes baseline tests
