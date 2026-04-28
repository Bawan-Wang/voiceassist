# 014 — Unify `SEARCH_TOKENS` / `is_search_intent`

## Status: Planned 🟡

## Motivation

Search-intent detection is currently duplicated:

- [src/api/app.py](../../src/api/app.py) lines 69–76 —
  `SEARCH_TOKENS` tuple (18 tokens) + inline
  `any(tok in text for tok in SEARCH_TOKENS)` check inside
  `zero_assistant()`.
- [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
  lines 108–117 — `_SEARCH_TOKENS` tuple (same 18 tokens,
  byte-identical) + `is_search_intent(text) -> bool` function used at
  line 364 to decide whether the bridge calls the websearch path or
  streams GPT-4o-mini directly.

Token sets are byte-for-byte identical; only the variable name differs
(`SEARCH_TOKENS` vs `_SEARCH_TOKENS`). Any future change has to land in
two places — the same trap that 013 just removed for the skill helpers.

[src/api/skills/tokens.py](../../src/api/skills/tokens.py) is already
the chosen home for "import-cheap, dependency-free token logic" (its
docstring forbids FastAPI/OpenAI/subprocess imports so the voice bridge
can pull it in cheaply at startup). Today it owns `PHOTOFRAME_TOKENS`,
`BUNNY_TOKENS`, `VERB_TOKENS` and exports `matches_photoframe` /
`matches_bunny` / `is_local_skill`. Adding `SEARCH_TOKENS` +
`is_search_intent` there is the obvious next step.

This plan moves the constant + function into `tokens.py`, makes both
`app.py` and `voice_bridge.py` import the canonical version, and keeps
behaviour identical (same tokens, same `any(tok in text)` semantics).

Out of scope:

- `command_tokens` / `rabbit_tokens` / `helper_tokens` in
  `voice_bridge.py` (specific to wake-word fallback, used nowhere else).
- Touching the routing decision tree in `app.py` or the bridge — only
  the *detection primitive* moves.
- Remaining tech-debt items (`AssistRequest.language/source`,
  `_should_route_without_wake` length fallback, `DEFAULT_VOICE` typo).

---

## Pre-flight

- [ ] Confirm 013 has shipped: `git log --oneline | grep 013` →
      expect `22d4d5d`.
- [ ] Snapshot baseline tests: `.venv/bin/pytest -q` → expect **65 passed**.
- [ ] `git status -s` clean.

---

## Phase A — Add canonical implementation

### Step 1 — Extend `src/api/skills/tokens.py`

Append (after `BUNNY_TOKENS` / `VERB_TOKENS`, before `_has_any`):

```python
SEARCH_TOKENS = (
    "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
    "網路上", "網頁", "資料", "天氣",
    "weather", "search", "look up", "find", "browse",
)


def is_search_intent(text: str) -> bool:
    """Return True if the command looks like a search/browse request.

    Pure substring match — kept identical to the legacy implementations
    in ``src/api/app.py`` and ``src/bridge/voice_bridge.py`` to avoid
    behaviour drift during the refactor.
    """
    if not text:
        return False
    return any(tok in text for tok in SEARCH_TOKENS)
```

Notes:

- Use a **tuple** (not a set) to preserve iteration order from the
  current code — purely cosmetic but keeps `git diff` minimal.
- Add an explicit empty-string guard (matches `_has_any` style; both
  legacy copies happened to short-circuit safely on `""` because
  `any()` over substring-in-empty returns False, so this is defence in
  depth, not a behaviour change).

---

## Phase B — Switch callers (depends on A)

### Step 2 — Update `src/api/app.py`

- Delete the local `SEARCH_TOKENS = (...)` tuple (lines ~69–75).
- Replace `is_search = any(tok in text for tok in SEARCH_TOKENS)` with:
  ```python
  from .skills.tokens import is_search_intent
  ...
  is_search = is_search_intent(text)
  ```
  (Import goes near the other `from .skills...` imports if any, else at
  module top.)
- Leave the `VOICEASSIST_DISABLE_WEBSEARCH` env check, the
  `meta["search"] = True` setting on line 83, and the
  `meta["search"] = is_search` setting on line 117 untouched.

### Step 3 — Update `src/bridge/voice_bridge.py`

- Delete the local `_SEARCH_TOKENS = (...)` tuple (lines 108–112).
- Delete the local `is_search_intent()` function (lines 114–117).
- Extend the existing lazy-import block (lines 121–127) to also pull
  in `is_search_intent`:
  ```python
  try:
      from src.api.skills.tokens import is_local_skill, is_search_intent  # noqa: F401
  except Exception:  # pylint: disable=broad-except
      def is_local_skill(text: str) -> bool:  # type: ignore[no-redef]
          return False
      def is_search_intent(text: str) -> bool:  # type: ignore[no-redef]
          return False
  ```
  Rationale for keeping the fallback: `voice_bridge.py` already does
  this for `is_local_skill` so a broken / missing skills package can't
  take down the audio loop. Mirror the pattern.
- The call site at line 364 (`searching = is_search_intent(command)`)
  stays unchanged because the imported symbol has the same name.

---

## Phase C — Tests (depends on B)

### Step 4 — Add a token-level test in `tests/test_skills.py`

Inside the existing `TestTokens` class, add:

```python
@pytest.mark.parametrize("text,expected", [
    ("幫我查台北天氣", True),
    ("搜尋最新新聞", True),
    ("找一下附近餐廳", True),
    ("look up the weather", True),
    ("你好", False),
    ("打開相框", False),
    ("", False),
])
def test_is_search_intent(self, text, expected):
    from src.api.skills.tokens import is_search_intent
    assert is_search_intent(text) is expected
```

This locks the canonical behaviour at the unit level so future
refactors can lean on it without round-tripping through FastAPI.

### Step 5 — Repoint `tests/test_intent.py`

`tests/test_intent.py` currently does
`from src.bridge.voice_bridge import is_search_intent`. After Step 3 the
symbol is re-exported from the bridge module's namespace via the lazy
import, so the import keeps working — but to make the canonical home
explicit, change the import to:

```python
from src.api.skills.tokens import is_search_intent
```

Existing parametrize cases stay unchanged.

---

## Phase D — Verification (depends on C)

### Step 6 — Test suite

```
.venv/bin/pytest -q
```

Expected: **66 passed** (65 baseline + 1 new `test_is_search_intent`).

### Step 7 — Import smoke

```
.venv/bin/python -c "from src.api.app import app; \
    from src.api.skills.tokens import SEARCH_TOKENS, is_search_intent; \
    from src.bridge.voice_bridge import is_search_intent as bridge_isi; \
    assert bridge_isi is is_search_intent; print('ok', len(SEARCH_TOKENS))"
```

The `is` check confirms the bridge ended up with the canonical function
object, not a lingering local definition or a fallback stub.

### Step 8 — Grep sweep

```
grep -RIn 'SEARCH_TOKENS\|is_search_intent' src/ tests/
```

Expect:

- definition lines only in `src/api/skills/tokens.py`
- import / use lines in `src/api/app.py`, `src/bridge/voice_bridge.py`,
  `tests/test_skills.py`, `tests/test_intent.py` (and `tests/test_api.py`
  hits remain on the `meta["search"]` field, not on the helper).
- **No** definition of `_SEARCH_TOKENS` anywhere.

### Step 9 — Live verification (await user OK)

After explicit user approval, restart and re-run the four 012/013 smoke
curls plus a search query to make sure the bridge path is unchanged:

```
./rabbitctl.sh restart

curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"打開相框"}'   | jq    # local-skill / open_photoframe
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"切回兔兔"}'   | jq    # local-skill / open_bunny
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"你好"}'       | jq    # fallback-openai, search=False
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"幫我查台北天氣"}' | jq # openai-websearch, search=True
```

Optionally speak "兔兔助理 幫我查台北天氣" to the mic to exercise the
voice-bridge search path end-to-end (the search-hint TTS should fire
before the websearch result arrives).

---

## Phase E — Wrap-up (requires user approval at each gate)

### Step 10 — Docs

- `.docs/tech-debt.md`: add a Resolved row referencing 014 for the
  SEARCH_TOKENS duplication.
- `.docs/context.md`: append `014 ✅` notes (mirror the 013 entry style).
- `PLAN.md`: add Phase 15 = 014 ✅ row; add 014 to the archived list.

### Step 11 — Archive plan

```
mv .docs/exec-plans/014-unify-search-tokens.md .docs/exec-plans/done/
```

### Step 12 — Commit (await user OK)

Single commit:

```
refactor(014): unify SEARCH_TOKENS / is_search_intent in skills.tokens

- Move the 18-token SEARCH_TOKENS tuple and is_search_intent() helper
  into src/api/skills/tokens.py (the dependency-free token module).
- src/api/app.py now imports is_search_intent from .skills.tokens
  instead of defining its own copy.
- src/bridge/voice_bridge.py extends its lazy skills-package import to
  pull in is_search_intent alongside is_local_skill; the local copy is
  removed.
- tests/test_skills.py: add test_is_search_intent at the unit level so
  the canonical behaviour is locked without going through FastAPI.
- tests/test_intent.py: re-target the import at the canonical home in
  src.api.skills.tokens.

No behaviour change. pytest 66 passed. Live curl smoke 4/4 OK.
```

### Step 13 — Push (await user OK)

`git push origin main` only after explicit approval.

---

## Relevant files

- `src/api/skills/tokens.py` — add `SEARCH_TOKENS` tuple +
  `is_search_intent()` (canonical home).
- `src/api/app.py` — drop local `SEARCH_TOKENS`; import
  `is_search_intent` from `.skills.tokens`; call site becomes one line.
- `src/bridge/voice_bridge.py` — drop local `_SEARCH_TOKENS` and
  `is_search_intent()`; extend the existing lazy import; call site at
  line 364 unchanged.
- `tests/test_skills.py` — add `test_is_search_intent` parametrize.
- `tests/test_intent.py` — re-point import to
  `src.api.skills.tokens` (same symbol name, no behavioural assertion
  changes).
- `.docs/tech-debt.md`, `.docs/context.md`, `PLAN.md` — Phase E docs.

## Verification summary

1. `.venv/bin/pytest -q` → 66 passed (was 65, +1 new unit test).
2. Import smoke: `bridge.is_search_intent is tokens.is_search_intent`
   evaluates True (proves single source of truth).
3. Grep: `_SEARCH_TOKENS` not present anywhere; `SEARCH_TOKENS` defined
   only in `tokens.py`.
4. Live curl after restart — 4/4 routes return correct
   `meta.source` + `meta.search`; voice-bridge spoken search query
   triggers the search-hint TTS as before.
5. `git diff --stat` ≈ +25 / −22 net (mostly a move).

## Decisions

- **Canonical home is `tokens.py`** — already designed as the
  dependency-free token module; both callers already either import from
  it (`voice_bridge`) or trivially can (`app`).
- **Keep tuple ordering, keep substring semantics** (no switch to set
  / regex / case-folding) — the goal is dedup, not behaviour change.
  Any future change to the matcher then lands in one place.
- **Voice bridge keeps its lazy-import fallback** so a broken skills
  package can't take down the audio loop. Same pattern already used for
  `is_local_skill`.
- **Add a unit test** in `test_skills.py` so the canonical behaviour
  has a fast assertion that doesn't require spinning up FastAPI.
- **Out of scope**: routing tree changes, other duplicated token sets
  in `voice_bridge.py` (`command_tokens`, `rabbit_tokens`,
  `helper_tokens`), tech-debt items unrelated to search detection.
- **No commit / push / device restart** without explicit user approval
  (AGENTS.md).
