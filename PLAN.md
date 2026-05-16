# PLAN.md — voiceassist Global Blueprint

## Project Goal

A local voice assistant running on Raspberry Pi that:
- Listens for a wake word, transcribes speech (Sherpa-ONNX STT)
- Routes intents to a FastAPI backend or directly to OpenAI GPT-4o-mini
- Responds via local Piper TTS
- Optionally controls a photoframe UI and a bunny face display

## Current Architecture

```
src/bridge/voice_bridge.py   Mic → VAD → STT → wake word → intent routing → TTS
src/api/app.py               FastAPI backend — local skills + websearch (search/weather) + OpenAI fallback
src/ui/assistant_ui.py       PyGame bunny face UI
tests/                       Pytest harness
.docs/                       Specs, architecture, exec plans, rules
```

## Overall Progress

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project scaffolding & environment setup | ✅ Done |
| 2 | Voice pipeline (STT + wake word + TTS) | ✅ Done |
| 3 | FastAPI intent routing + OpenAI/websearch | ✅ Done |
| 4 | Bunny UI + photoframe integration | ✅ Done |
| 5 | Project restructure (`src/`, `.docs/`) + product specs | ✅ Done |
| 6 | Fix search returning raw error strings (exec-plan 005) | ✅ Done |
| 7 | LLM + `web_search` skill (exec-plan 006) | ✅ Done |
| 8 | Restore + modularize local skills (exec-plan 007) | ✅ Done |
| 9 | Photoframe smooth transitions (exec-plan 008) | ✅ Done |
| 12 | Drop OpenClaw fallback route (exec-plan 010) | ✅ Done |
| 13 | Drop deprecated hard-coded skill routes (exec-plan 012) | ✅ Done |
| 14 | Consolidate skill helpers + SIGNAL_PATH (exec-plan 013) | ✅ Done |
| 15 | Unify SEARCH_TOKENS / is_search_intent (exec-plan 014) | ✅ Done |
| 16 | Collapse module-level config globals into BridgeConfig (exec-plan 015) | ✅ Done |
| 17 | Collapse config to yaml-only source of truth (exec-plan 016) | ✅ Done |
| 18 | Fix dependency manifests + clean-install baseline (exec-plan 017) | ✅ Done |
| 19 | Add GitHub-hosted CI + code scanning baseline (exec-plan 018A) | ✅ Done |
| 20 | Add Raspberry Pi self-hosted hardware smoke workflow (exec-plan 018B) | ✅ Done |
| 21 | Shared routing policy (exec-plan 020) | ✅ Done |
| 22 | Plan time queries, reminders, and memory as the next product surface | 📝 Planned |

## Active Exec Plans

- [021 — Implement Time Queries](.docs/exec-plans/021-implement-time-queries.md) — Planned 📝

## Next Product Work

The next planned user-facing capability set is:

1. Time queries
2. Reminders
3. Memory

These three areas are intentionally sequenced in that order:

- Time queries are the smallest deterministic skill surface and should be the
  first implementation target.
- Reminders depend on time parsing, normalization, and delivery behavior, so
  they should follow after the time-query rules are stable.
- Memory should come last because it changes cross-feature behavior and needs a
  tighter product boundary than the first two features.

Current planning status:

- `.docs/product-specs/time-queries.md` exists as a planned skeleton and still
  needs to be expanded into a full implementation-ready spec.
- `.docs/product-specs/reminders.md` exists as a planned skeleton and still
  needs to be expanded into a full implementation-ready spec.
- `.docs/product-specs/memory.md` exists as a planned skeleton and still needs
  to be expanded into a full implementation-ready spec.

Do not start implementation from these skeleton specs alone. The expected flow
for this product area is:

1. Complete `time-queries.md` as the first full spec.
2. Complete `reminders.md` with explicit confirmation, persistence, and due-time behavior.
3. Complete `memory.md` with a narrow first-phase scope.
4. After the specs are fully defined, create the corresponding exec-plan(s) and implement in the same order.

## Done (archived)

See `.docs/exec-plans/done/` — includes 001 (env), 002 (vlm-bridge), 003
(taiwan-racing-fix), 004 (voice-bridge-relative-import), 005 (search-error-reply),
006 (llm-websearch-skill), 007 (restore-and-modularize-local-skills),
008 (photoframe-smooth-transitions), 009 (docs-drop-openclaw-route),
010 (remove-openclaw-route), 011 (drop-stale-roadmap-rows),
012 (drop-deprecated-skill-routes), 013 (consolidate-skill-helpers),
014 (unify-search-tokens), 015 (collapse-config-globals),
016 (yaml-source-of-truth), 017 (dependency-manifests-clean-install),
018A (github-hosted-ci-and-code-scanning-baseline),
018B (raspberry-pi-self-hosted-hardware-smoke),
019 (document-voice-vs-http-entrypoints),
020 (shared-routing-policy).
