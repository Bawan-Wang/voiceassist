# 019 — Document Voice vs HTTP Entrypoints

## Status: Planned 🟡

## Motivation

The repository has two different runtime entrypoints today:

- The voice runtime in [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
- The HTTP text endpoint in [src/api/app.py](../../src/api/app.py)

They share some helpers, but they do **not** start from the same stage of the
pipeline and they do **not** make routing decisions in exactly the same place.
That difference is easy to lose when reading the code because:

- [three-routing-paths.md](../technical-concepts/three-routing-paths.md)
  starts after text already exists, so it does not explain how a request
  enters the system.
- [architecture.md](../architecture.md) notes that the two entrypoints differ,
  but only briefly.
- Questions like "does HTTP own the LLM path?" or "why does voice sometimes
  bypass the API?" require opening several files and mentally stitching them
  together.

This plan adds one canonical technical-concepts document that explains:

- what the voice entrypoint does before text exists,
- what the HTTP entrypoint does once text exists,
- which modules are truly shared,
- where the routing decisions diverge today,
- and which source files own each part of the behavior.

019 is intentionally **documentation-only**. It documents the architecture as
it exists before 020 introduces a shared routing policy.

---

## Pre-flight

- [ ] Confirm there is no active unmerged doc rewrite under `.docs/technical-concepts/`
      that would conflict with a new `entrypoints.md` page.
- [ ] Confirm 020 has **not** landed yet; this document must describe the
      current split-entrypoint behavior, not the target architecture.
- [ ] Skim [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) and
      [src/api/app.py](../../src/api/app.py) before writing so the doc reflects
      the current control flow, not stale assumptions.

---

## Action Items

### Step 1 — Add a new technical-concepts page

- [ ] Create [../technical-concepts/entrypoints.md](../technical-concepts/entrypoints.md).
- [ ] Make it the canonical answer to: "What is the difference between the
      voice entrypoint and the HTTP entrypoint?"
- [ ] Keep the page focused on current runtime behavior, not future design.

Recommended outline:

```text
1. Why there are two entrypoints
2. Voice entrypoint: activation, pre-routing stages, routing, execution
3. HTTP entrypoint: request shape, routing, execution
4. Shared helpers and code ownership
5. Current divergence points
6. Example request walk-throughs
7. Note: this page documents pre-020 architecture
```

### Step 2 — Document the voice entrypoint in detail

- [ ] Explain that the voice entrypoint is the long-lived runtime in
      [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py).
- [ ] Anchor the explanation on `VoiceBridge.run()` and the surrounding helpers.
- [ ] Cover the stages **before** routing exists:
  - audio capture,
  - VAD,
  - STT,
  - wake-word matching,
  - pending wake follow-up,
  - auto-route without wake.
- [ ] Cite the voice-specific decision points:
  - `_match_wake_phrase()`
  - `_should_route_without_wake()`
  - local-skill raw-transcript fallback
  - direct GPT streaming path
- [ ] Make explicit that the voice runtime can either:
  - call the local HTTP API via `_reply_via_api()`, or
  - talk to OpenAI directly via `_reply_via_gpt4o_mini()` /
    `stream_reply_and_speak()`.

### Step 3 — Document the HTTP entrypoint in detail

- [ ] Explain that the HTTP entrypoint is `POST /zero-assistant` in
      [src/api/app.py](../../src/api/app.py).
- [ ] Explain that it receives already-transcribed text and therefore does
      **not** own audio capture, VAD, STT, wake-word handling, or TTS.
- [ ] Document the current routing order:
  1. `match_skill(text)`
  2. `is_search_intent(text)`
  3. plain OpenAI fallback
- [ ] Document the returned contract:
  - `reply_text`
  - `meta.source`
  - `meta.action`
  - `meta.search`

### Step 4 — Document the genuinely shared surfaces

- [ ] Add a section listing the code that is used by both entrypoints today:
  - [src/api/skills/tokens.py](../../src/api/skills/tokens.py)
  - [src/api/skills/__init__.py](../../src/api/skills/__init__.py)
  - [src/api/websearch.py](../../src/api/websearch.py)
- [ ] For each shared module, state what it owns and what it does **not** own.
- [ ] Make it explicit that the repo currently shares helpers, but not one
      unified routing decision function.

### Step 5 — Add side-by-side diagrams and examples

- [ ] Add one ASCII diagram for the voice entrypoint.
- [ ] Add one ASCII diagram for the HTTP entrypoint.
- [ ] Add a comparison table covering:
  - trigger source,
  - input type,
  - wake-word handling,
  - routing owner,
  - direct LLM usage,
  - HTTP usage,
  - TTS responsibility,
  - response shape.
- [ ] Add three walk-through examples:
  - a local skill phrase,
  - a search phrase,
  - a normal chat phrase.

### Step 6 — Cross-link from existing docs

- [ ] Update [../technical-concepts/three-routing-paths.md](../technical-concepts/three-routing-paths.md)
      with a short preamble saying that its three paths begin **after** text is
      already available, and point readers to `entrypoints.md` for how a request
      enters the system.
- [ ] Update [../architecture.md](../architecture.md) to cross-link the new
      `entrypoints.md` page from the existing "Two Runtime Entry Paths" section.
- [ ] Review [../product-specs/intent-routing.md](../product-specs/intent-routing.md)
      and [../api.md](../api.md) for wording that accidentally implies a single
      runtime entrypoint; adjust only if needed for clarity.

### Step 7 — Preserve room for 020

- [ ] Add a brief note in the new page that the document reflects the
      pre-020 architecture.
- [ ] Avoid language that would need a full rewrite once 020 lands; prefer
      phrasing like "today" / "currently" for divergence points.

---

## Acceptance Criteria

- [ ] A new file exists at
      [../technical-concepts/entrypoints.md](../technical-concepts/entrypoints.md).
- [ ] The new page clearly explains the difference between:
  - the voice runtime entrypoint, and
  - the HTTP text entrypoint.
- [ ] The page names the shared modules and also states that the routing policy
      itself is still duplicated today.
- [ ] The page includes source-code anchors to at least:
  - [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
  - [src/api/app.py](../../src/api/app.py)
  - [src/api/skills/tokens.py](../../src/api/skills/tokens.py)
  - [src/api/skills/__init__.py](../../src/api/skills/__init__.py)
  - [src/api/websearch.py](../../src/api/websearch.py)
- [ ] [three-routing-paths.md](../technical-concepts/three-routing-paths.md)
      and [architecture.md](../architecture.md) both cross-link to the new page.
- [ ] No runtime code changes are made.
- [ ] No test run is required unless a non-doc file is touched.

---

## Rollback Plan

Pure documentation change. If the page is misleading or 020 lands first with a
different architecture than expected, revert the docs commit and rewrite the
page against the new routing model.

---

## Out of Scope

- Changing any routing behavior in
  [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) or
  [src/api/app.py](../../src/api/app.py)
- Extracting a shared routing policy module
- Unifying transport so all voice traffic flows through the HTTP API
- Rewriting TTS or streaming behavior
- Editing files under `.docs/exec-plans/done/` (historical record)
