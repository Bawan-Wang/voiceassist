# rules.md — Coding Style & Conventions

This file complements `AGENTS.md` and `CLAUDE.md`.

- `AGENTS.md` owns workflow rules and required reading.
- `CLAUDE.md` is a thin compatibility shim that points here.
- This file owns behavioral guidance, repository-specific coding conventions,
  and the list of
  currently-known deviations from those conventions.

## How To Apply These Rules

- Use these rules as the default for new code and touched lines.
- Do not widen a change only to force untouched code into compliance.
- When a rule conflicts with already-tracked code, prefer the local style of
  the file unless the task is explicitly a cleanup.

## Behavioral Guidance

### Think Before Coding

- State assumptions explicitly instead of silently guessing.
- If multiple interpretations exist, surface them instead of picking one
  without saying so.
- If something is unclear, stop and ask or document the uncertainty.
- If a simpler approach exists, prefer it and say why.

### Simplicity First

- Write the minimum code that solves the requested problem.
- Do not add speculative flexibility, configurability, or abstractions that
  were not requested.
- Do not add error handling for scenarios that are not realistic for the task.
- If the implementation feels larger than the problem, simplify it.

### Surgical Changes

- Touch only the lines needed for the request.
- Do not refactor adjacent code just because you noticed it.
- Match the surrounding file style unless the task is explicitly a cleanup.
- Clean up imports, variables, or helpers only when your own change made them
  unused.

### Goal-Driven Execution

- Turn vague requests into verifiable success criteria before editing.
- For multi-step work, keep a short plan with one clear verification check per
  step.
- Prefer tests or targeted validation over subjective "looks right" checks.

## Current Repository Deviations

The following rules are not yet fully true across the existing codebase. They
should be treated as migration targets for future cleanup, not as permission to
do unrelated refactors.

- `No print() in src` currently conflicts with tracked code in `src/api/app.py`,
  `src/bridge/voice_bridge.py`, and `src/bridge/providers/common.py`.
- `No synchronous blocking I/O in FastAPI route handlers` currently conflicts
  with `src/api/app.py::zero_assistant()`, which is still a synchronous route
  and performs blocking work.
- `No direct subprocess.run without timeout` currently conflicts with tracked
  code in `src/api/skills/_process_utils.py`, `src/api/skills/open_bunny.py`,
  `src/api/skills/open_photoframe.py`, and `src/bridge/voice_bridge.py`.

## Language & Runtime

- **Python 3.11** — no walrus operator in test files for 3.9 compat (not applicable here, but keep in mind)
- All source code under `src/` — import as `from src.api.app import ...`
- Virtual env: `.venv/` — always use `.venv/bin/python` or `.venv/bin/pytest`

## Coding Style

- Follow **PEP 8** — 4-space indentation, max line length 100
- Type hints on all public functions
- Docstrings on all modules and public classes/functions (Google style)
- No bare `except:` — always catch specific exceptions

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions / variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Config keys in `config.yaml`: `camelCase` (existing convention — do not change)

## Forbidden

The items below are target conventions for new or modified code. Existing
deviations are documented above.

- **No `print()` in `src/`** — use `logging` instead
- **No hardcoded API keys** — read from env or `config.yaml`
- **No synchronous blocking I/O in FastAPI route handlers** — use `asyncio` or run in threadpool
- **No direct `subprocess.run` without timeout** — always set `timeout=` argument

## Testing

- Every new feature in `src/api/app.py` → test in `tests/test_api.py`
- Every new logic function in `src/bridge/` → unit test in appropriate `tests/test_*.py`
- Run tests before reporting completion: `.venv/bin/pytest tests/ -v`
- All tests must pass — no skipping without a comment explaining why

## Git

- Never commit without explicit user approval
- Commit messages: imperative mood, English, e.g. `Move api/ bridge/ ui/ into src/`
