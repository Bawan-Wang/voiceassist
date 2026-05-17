# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- `.docs/product-specs/smoke-tests.md` — manual smoke test list and regression negative cases (tests + acceptance criteria).
- 022: Implement one-time reminders — deterministic parser/normalizer, durable JSON storage, pending clarification flow, and idle-only voice delivery.

### Fixed
- Reminder parsing now accepts second-based relative reminders such as `5秒鐘後提醒我吃藥`, and the API reminder confirmation test no longer depends on a hard-coded late-night clock.
- 023: Fix routing false positives — tighten LOCAL_SKILL and TIME_QUERY matchers; add regression tests and docs. (Commit a7e741e)
  - Bare noun mentions like "兔兔" and "相框" no longer trigger local-skill routes by themselves.
  - Conversational "我有時間嗎" / "你有時間嗎" are no longer treated as time queries.
  - See `.docs/exec-plans/023-fix-routing-false-positives.md` and `.docs/product-specs/smoke-tests.md` for details and examples.

### Commit references
- a7e741e — 023: fix routing false positives — tighten LOCAL_SKILL and TIME_QUERY matchers; add tests and docs
- 4adff92 — docs: add smoke-tests for routing/local-skill/time-query

