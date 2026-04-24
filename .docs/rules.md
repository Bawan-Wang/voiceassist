# rules.md — Coding Style & Conventions

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
