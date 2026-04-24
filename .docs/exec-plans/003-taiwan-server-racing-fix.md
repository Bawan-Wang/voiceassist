# 003 — Taiwan Server Racing Fix

## Status: Planned 🔲

## Goal
Fix the race condition where concurrent requests to the Taiwan-hosted OpenClaw server
cause timeout collisions and incorrect fallback behaviour.

## Root Cause (Hypothesis)
- Voice bridge fires `POST /zero-assistant` while a previous request is still pending
- Second request hits `timeout=90s` and falls back to OpenAI, giving inconsistent replies
- No request queue or in-flight guard currently in place

## Proposed Fix
- Add an `asyncio.Lock` or a simple `is_processing` flag in `src/api/app.py`
- If a request arrives while one is in flight, either queue it or return a "busy" response immediately
- Voice bridge should handle `{"busy": true}` reply gracefully (speak "稍等一下")

## Acceptance Criteria
- [ ] Rapid successive voice triggers do not produce duplicate or interleaved replies
- [ ] `tests/test_api.py` includes a concurrent-request test case
- [ ] No regression on existing `pytest tests/ -v`
