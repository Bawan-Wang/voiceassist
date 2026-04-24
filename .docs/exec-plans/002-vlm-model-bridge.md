# 002 — VLM Model Bridge

## Status: Planned 🔲

## Goal
Integrate a Vision-Language Model (VLM) so the assistant can answer questions about camera input or uploaded images.

## Proposed Approach
- Add a new intent type `vision` detected in `src/bridge/voice_bridge.py`
- Capture a frame from the camera (or accept an image path)
- Send image + text prompt to a VLM endpoint (e.g., LLaVA via Ollama, or GPT-4o vision)
- Return description/answer via TTS

## Open Questions
- [ ] Which VLM backend? Local (Ollama + LLaVA) vs remote (GPT-4o)?
- [ ] Camera interface: `picamera2` or OpenCV?
- [ ] Latency budget: acceptable response time on Pi hardware?

## Acceptance Criteria
- [ ] User says "看一下這個" → camera captures frame → VLM responds via TTS
- [ ] New `tests/test_vlm_bridge.py` with mocked VLM call passes
- [ ] No regression on existing `pytest tests/ -v`
