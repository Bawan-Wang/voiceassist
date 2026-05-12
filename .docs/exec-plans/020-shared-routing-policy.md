# 020 — Shared Routing Policy

## Status: Planned 🟡

## Motivation

Today the repository has **two runtime entrypoints** and **two copies of the
routing decision tree**:

- [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) decides inside
  `VoiceBridge.run()` whether a request is a local skill, a search/tool-needed
  request, or normal chat.
- [src/api/app.py](../../src/api/app.py) decides inside `POST /zero-assistant`
  whether the text is a local skill, a search request, or a plain OpenAI
  fallback.

The duplication is subtle because the repo already shares some primitives:

- `is_local_skill()` / `is_search_intent()` in
  [src/api/skills/tokens.py](../../src/api/skills/tokens.py)
- `match_skill()` in
  [src/api/skills/__init__.py](../../src/api/skills/__init__.py)

But the final policy is still split across two call sites, which creates drift
pressure:

- changes to precedence have to land in more than one place,
- the bridge owns a raw-transcript recovery rule that the API never sees,
- docs have to explain two near-identical but separately maintained trees,
- tests validate behavior at multiple layers without one canonical classifier.

The goal of 020 is to introduce **one shared routing policy** after text is
available, while keeping the current execution backends intact:

- local skill execution stays deterministic,
- search/tool-needed requests still use the API websearch path,
- chat in the voice bridge still uses the direct streaming GPT path.

020 is **not** an API-first rewrite and **not** a transport unification plan.
It unifies classification first because that is the lowest-risk slice.

---

## Pre-flight

- [ ] Confirm 019 has either landed or is ready to land, so the pre-020 split
      architecture is documented before refactoring it.
- [ ] Snapshot current routing tests:
      `cd /home/jh-pi/.openclaw/workspace/voiceassist && .venv/bin/pytest -q`
- [ ] Confirm the current skill/token helpers still live in:
  - [src/api/skills/__init__.py](../../src/api/skills/__init__.py)
  - [src/api/skills/tokens.py](../../src/api/skills/tokens.py)
- [ ] Confirm no parallel branch is already introducing a `policy.py` or other
      new routing abstraction under `src/api/skills/`.

---

## Target Architecture

```text
text available
   |
   v
shared classify_request(...)
   |
   +-- LOCAL_SKILL  -> deterministic skill executor
   +-- TOOL_NEEDED  -> websearch / tool path via API
   '-- CHAT         -> direct chat executor

voice_bridge.py
   -> wake / STT / raw transcript recovery remain local
   -> calls shared classifier once
   -> keeps existing executors (API for local/search, streaming GPT for chat)

api/app.py
   -> receives text JSON
   -> calls shared classifier once
   -> keeps existing executors (skill.run, websearch, OpenAI fallback)
```

The key invariant after 020:

- for the same text, the bridge and the API produce the same route kind,
- while still being allowed to use different executors for the final response.

---

## Action Items

### Step 1 — Add a shared routing policy module

- [ ] Create [src/api/skills/policy.py](../../src/api/skills/policy.py).
- [ ] Add a small explicit API, e.g.:

  ```python
  class RouteKind(Enum):
      LOCAL_SKILL = "local_skill"
      TOOL_NEEDED = "tool_needed"
      CHAT = "chat"

  @dataclass
  class RouteDecision:
      kind: RouteKind
      routed_text: str
      skill: Any | None = None
      is_search: bool = False
      used_raw_transcript: bool = False

  def classify_request(text: str, *, raw_transcript: str | None = None) -> RouteDecision:
      ...
  ```

- [ ] Keep this module dependency-light so the bridge can import it cheaply.
- [ ] Reuse existing helpers instead of re-encoding tokens in a third place.

### Step 2 — Define policy precedence explicitly

- [ ] Lock the route order to:
  1. local skill,
  2. tool-needed/search,
  3. chat.
- [ ] Preserve the current bridge-only raw transcript recovery behavior:
  - first evaluate `text`,
  - then, for local skills only, allow fallback to `raw_transcript` when
    `text` lost the noun during wake stripping.
- [ ] Do **not** infer new tool-needed categories in 020 beyond the current
      search/weather behavior.

### Step 3 — Switch the HTTP API to the shared policy

- [ ] Refactor [src/api/app.py](../../src/api/app.py) so `zero_assistant()`
      calls `classify_request(text)` once.
- [ ] Replace the separate `match_skill()` and `is_search_intent()` branching
      with `RouteDecision` handling.
- [ ] Preserve current execution semantics:
  - `LOCAL_SKILL` -> `decision.skill.run()`
  - `TOOL_NEEDED` -> `run_websearch()` then plain OpenAI fallback on failure
  - `CHAT` -> plain OpenAI fallback
- [ ] Preserve backward-compatible response metadata:
  - `meta.source == "local-skill"`
  - `meta.source == "openai-websearch"`
  - `meta.source == "fallback-openai"`
  - `meta.action` and `meta.search` remain stable.

### Step 4 — Switch the voice bridge to the shared policy

- [ ] Refactor [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
      so `VoiceBridge.run()` calls:

  ```python
  decision = classify_request(command, raw_transcript=transcript)
  ```

- [ ] Replace the inline `is_local_skill(...)` / `is_search_intent(...)`
      branching in `run()` with one `RouteDecision` switch.
- [ ] Preserve current executors:
  - `LOCAL_SKILL` -> `_reply_via_api(decision.routed_text)`
  - `TOOL_NEEDED` -> speak the search hint, then `_reply_via_api(command)`
  - `CHAT` -> `stream_reply_and_speak(command)`
- [ ] Keep wake-word handling, `_should_route_without_wake()`, and raw audio
      lifecycle logic outside the new policy.

### Step 5 — Keep transport boundaries intact in this phase

- [ ] Leave `_reply_via_api()` in
      [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) intact.
- [ ] Leave `_reply_via_gpt4o_mini()` and `stream_reply_and_speak()` intact.
- [ ] Remove only trivial wrappers if they become obviously redundant
      after the classifier lands.
- [ ] Do **not** force normal chat through the HTTP API in 020.

### Step 6 — Add policy-level tests

- [ ] Create [tests/test_routing_policy.py](../../tests/test_routing_policy.py).
- [ ] Cover at least:
  - local skill beats search-token collisions,
  - search becomes `TOOL_NEEDED`,
  - normal chat becomes `CHAT`,
  - raw transcript fallback still catches the wake-stripper case,
  - the returned `routed_text` is correct.

Suggested cases:

- [ ] `打開相框` -> `LOCAL_SKILL`
- [ ] `切回兔兔` -> `LOCAL_SKILL`
- [ ] `幫我查新北天氣` -> `TOOL_NEEDED`
- [ ] `你好` -> `CHAT`
- [ ] `text="切回"`, `raw_transcript="兔兔助理切回兔兔"` -> `LOCAL_SKILL`

### Step 7 — Update caller tests

- [ ] Update [tests/test_api.py](../../tests/test_api.py) so it continues to
      validate the response contract after the internal routing refactor.
- [ ] Update [tests/test_voice_bridge_local_routing.py](../../tests/test_voice_bridge_local_routing.py)
      so it validates shared-policy behavior, not just token helper behavior.
- [ ] Keep [tests/test_intent.py](../../tests/test_intent.py) and
      [tests/test_skills.py](../../tests/test_skills.py) as the low-level
      helper tests unless the refactor makes them redundant.

### Step 8 — Update docs to match the new model

- [ ] Update [../technical-concepts/entrypoints.md](../technical-concepts/entrypoints.md)
      from 019 so it explains that the two entrypoints now share a classifier
      but still use different executors.
- [ ] Update [../architecture.md](../architecture.md) so the "Two Runtime Entry
      Paths" section no longer says the bridge and API make different routing
      decisions.
- [ ] Update [../product-specs/intent-routing.md](../product-specs/intent-routing.md)
      so the decision tree starts with the shared classifier.
- [ ] Update [../technical-concepts/three-routing-paths.md](../technical-concepts/three-routing-paths.md)
      with a short section explaining "shared classification, separate
      executors".

### Step 9 — Verify in layers

- [ ] Run the new policy test file first.
- [ ] Run the routing-slice tests next.
- [ ] Run the full baseline suite after the slice is green.
- [ ] Finish with a live smoke pass through the voice runtime:
  - one local skill phrase,
  - one search phrase,
  - one normal chat phrase.

---

## Acceptance Criteria

- [ ] A new shared policy module exists at
      [src/api/skills/policy.py](../../src/api/skills/policy.py).
- [ ] Both [src/api/app.py](../../src/api/app.py) and
      [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) call the
      shared policy instead of maintaining separate route trees.
- [ ] The API response contract remains backward compatible.
- [ ] The voice bridge still preserves the raw-transcript local-skill fallback.
- [ ] The voice bridge still streams chat responses sentence-by-sentence.
- [ ] `pytest tests/test_routing_policy.py -q` passes.
- [ ] The routing-focused slice passes:

  ```bash
  cd /home/jh-pi/.openclaw/workspace/voiceassist
  .venv/bin/pytest tests/test_api.py tests/test_voice_bridge_local_routing.py \
      tests/test_intent.py tests/test_skills.py -q
  ```

- [ ] The full suite passes:

  ```bash
  cd /home/jh-pi/.openclaw/workspace/voiceassist
  .venv/bin/pytest -q
  ```

- [ ] Live smoke confirms that local skill, search, and chat still reach their
      expected executors with no obvious latency regression.

---

## Rollback Plan

If the shared classifier introduces routing regressions:

1. Revert the commit that introduces `policy.py` and the two caller changes.
2. Restore the previous inline routing logic in
   [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) and
   [src/api/app.py](../../src/api/app.py).
3. Re-run the routing-slice tests and one live smoke pass.

Because 020 keeps the existing executors intact, rollback should be mechanical:
remove the shared decision layer and return to the two prior call-site trees.

---

## Out of Scope

- Making the HTTP API the single runtime entrypoint
- Streaming responses from `/zero-assistant`
- Rewriting wake-word matching or `_should_route_without_wake()` heuristics
- Redesigning TTS threading or Piper playback
- Adding new tool-needed categories beyond the current search/weather intent
- Collapsing transport code into a new transport abstraction in the same plan
