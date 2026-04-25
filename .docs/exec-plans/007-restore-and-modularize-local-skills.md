# 007 — Restore + Modularize Local Skills

## Status: Active 🔴

## Motivation

The "open photoframe / open bunny" voice commands silently broke: although
`src/api/app.py` still has `open_photoframe()` and `open_bunny_ui()`, the
**voice bridge never POSTs those phrases to `/zero-assistant`**. It only
forwards search-intent utterances; everything else streams from GPT-4o-mini.
So local commands work via curl/tests but **not via voice**.

This plan restores the voice path AND refactors the two hard-coded `if`
branches into a small skill registry, so future local commands (and the
upcoming local LLM tool-calling) have a clean extension point.

The user also wants "相簿 / 照片 / album / photos" to map to the same
photoframe app (it IS the album).

---

## Target Architecture

```
voice_bridge.py
   │
   ├─ is_local_skill(text)  ← NEW (cheap string match, src.api.skills.tokens)
   │      └─ YES → POST /zero-assistant      (no GPT)
   │
   ├─ is_search_intent(text)
   │      └─ YES → POST /zero-assistant
   │
   └─ everything else → direct GPT-4o-mini stream

api/app.py
   │
   ├─ match_skill(text)    ← NEW dispatcher
   │      └─ HIT → skill.run() → meta.source="local-skill", meta.action=<name>
   │
   ├─ search → websearch → openclaw → openai (existing)
   │
   └─ chitchat → openclaw → openai (existing)

src/api/skills/
   ├─ __init__.py        — SKILLS list, match_skill(), is_local_skill helpers
   ├─ tokens.py          — pure str sets, importable from voice_bridge w/o FastAPI
   ├─ open_photoframe.py — handles 相框/相簿/照片/photoframe/album/photos
   └─ open_bunny.py      — handles 兔兔/bunny
```

---

## IPC Convention (decoupled from data/demo_state.json)

`/tmp/voiceassist_signal.json` — single shared signal file owned by no module.

```json
{
  "bunny_should_exit": false,
  "photoframe_should_exit": false,
  "ts": 1777108412
}
```

- voiceassist skills WRITE the flags (atomic write via tempfile + rename).
- bunny UI READS `bunny_should_exit` (007).
- photoframe READS `photoframe_should_exit` (008, deferred).

---

## Action Items

### Step 1 — Create skills package

- [ ] `src/api/skills/__init__.py`
  - `SKILLS = [open_photoframe, open_bunny]`
  - `match_skill(text) -> Skill | None`
  - `is_local_skill(text) -> bool` (delegates to `tokens.matches()`)

- [ ] `src/api/skills/tokens.py` — pure-string helpers, NO FastAPI import:
  ```python
  PHOTOFRAME_TOKENS = {"相框", "相簿", "照片", "photoframe", "album", "photos"}
  BUNNY_TOKENS = {"兔兔", "bunny"}
  VERB_TOKENS = {"打開", "開啟", "切到", "切去", "切回", "回到"}
  def matches(text: str) -> str | None: ...   # returns skill name or None
  ```

- [ ] `src/api/skills/open_photoframe.py`
  - `NAME = "open_photoframe"`
  - `MATCH_TOKENS = PHOTOFRAME_TOKENS`
  - `def match(text) -> bool` (verb + noun)
  - `def run() -> str` — port existing `open_photoframe()` logic, plus:
    - Before launching, write `bunny_should_exit=true` to signal file
    - `time.sleep(0.5)` to let bunny fade out
    - Then kill PIDs as fallback (in case fade-out failed)
    - After launch, wait up to 1.0s for `/tmp/photoframe.ready`; if absent,
      return `"相框打不開，可能少裝套件，請看 /tmp/photoframe.log。"`
  - Replies: `"好的，已幫你打開相框。"` / `"相框已經是開啟狀態。"`

- [ ] `src/api/skills/open_bunny.py`
  - `NAME = "open_bunny"`
  - `MATCH_TOKENS = BUNNY_TOKENS`
  - `def run() -> str` — port existing `open_bunny_ui()`; clear
    `bunny_should_exit=false` before relaunching bunny
  - Replies: `"好的，已切回兔兔助理畫面。"` / `"兔兔畫面已經開啟。"`

### Step 2 — Refactor `src/api/app.py`

- [ ] Remove the two hard-coded `if "打開" in text...` blocks
- [ ] Replace with:
  ```python
  from .skills import match_skill
  hit = match_skill(text)
  if hit is not None:
      reply = hit.run()
      return AssistResponse(
          reply_text=reply,
          meta={"source": "local-skill", "action": hit.NAME},
      )
  ```
- [ ] Keep `BUNNY_CMD` / `PHOTO_CMD` constants but move them into the skill files

### Step 3 — Update `src/bridge/voice_bridge.py`

- [ ] Import `from src.api.skills.tokens import is_local_skill` (cheap, no FastAPI)
- [ ] In the routing block (around line 327), add BEFORE the search check:
  ```python
  if is_local_skill(command):
      reply = self._reply_via_api(command)   # forces API path
      ...
      return
  ```

### Step 4 — Harden `run_photoframe.sh`

- [ ] Add Kivy preflight:
  ```bash
  if ! python3 -c "import kivy" 2>>/tmp/photoframe.log; then
      echo "[$(date)] kivy import failed; aborting" >> /tmp/photoframe.log
      exit 2
  fi
  ```
- [ ] Keep `cd $WORKSPACE_DIR && exec python3 main.py` afterwards
- [ ] (No venv switch — photoframe uses system python3 with apt-installed kivy)

### Step 5 — Bunny fade-out (simple version)

- [ ] In `src/ui/assistant_ui.py`: poll `/tmp/voiceassist_signal.json` once per
      frame; on `bunny_should_exit == true`:
  - Run a 0.4s alpha 1→0 animation
  - Call `pygame.quit(); sys.exit(0)`
- [ ] Add helper `src/api/skills/_signal.py`:
  ```python
  SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")
  def write(**kwargs): ...   # atomic merge + write
  def clear_bunny_exit(): write(bunny_should_exit=False)
  def request_bunny_exit(): write(bunny_should_exit=True)
  ```

### Step 6 — Docs

- [ ] `.docs/skill.md` — new "Local Skills (callable via /zero-assistant)" section
      listing the 2 skills, tokens, target process, log paths; note "future
      local LLM can call these as tool-call targets"
- [ ] `.docs/product-specs/local-commands.md` — add 相簿/照片/album/photos
      tokens; document fade-out behavior; document `/tmp/voiceassist_signal.json`
- [ ] `.docs/product-specs/intent-routing.md` — add local-skill branch BEFORE
      search detection in the routing tree
- [ ] `PLAN.md` — phase 8 = 007 active
- [ ] `.docs/context.md` — current focus = 007

### Step 7 — Tests

- [ ] `tests/test_skills.py`
  - Token match table for both skills (positive + negative cases)
  - `open_photoframe.run()` with mocked subprocess + signal-file IO
  - `open_bunny.run()` symmetric
- [ ] `tests/test_voice_bridge_local_routing.py`
  - Mock STT result "打開相簿" → assert `_reply_via_api` is called,
    `_reply_via_gpt4o_mini` is NOT called
  - Same for "切回兔兔", "打開相框"
- [ ] Update `tests/test_api.py::TestLocalCommands`
  - Use the dispatcher; add cases for 相簿/照片/album
  - `meta.source == "local-skill"` instead of `"local-command"`
- [ ] `.venv/bin/pytest tests/ -v` — must end ≥ 40 passed (34 existing + ≥ 6 new)

---

## Acceptance Criteria

- [ ] Saying "兔兔助理 打開相框" → photoframe opens, bunny fades out smoothly
- [ ] Saying "兔兔助理 打開相簿" → same as above (alias works)
- [ ] Saying "兔兔助理 打開照片" → same as above
- [ ] Saying "兔兔助理 切回兔兔" → bunny reappears, photoframe killed
- [ ] If kivy not installed → photoframe NOT silently fails; user hears
      "相框打不開，可能少裝套件…" instead of "好的，已幫你打開相框。"
- [ ] `voice_bridge.log` shows `[voice_bridge] Local skill: open_photoframe`
      (not `Streaming reply`)
- [ ] curl POST `/zero-assistant` with `{"text":"打開相簿"}` returns
      `meta.source == "local-skill"`, `meta.action == "open_photoframe"`
- [ ] All pytest tests pass (≥ 40)
- [ ] Commit msg: `feat(007): restore + modularize local skills (photoframe/bunny)`

---

## Rollback Plan

If 007 breaks production:

1. `git revert <sha>` — voice bridge falls back to direct GPT for everything
2. Local commands still callable via direct curl (path unchanged in app.py
   if we keep the old `if` blocks as a thin shim) — actually safer: do NOT
   delete the old blocks until 007 is verified live. Mark them as deprecated
   with a `# TODO(007): remove after dispatcher verified` comment.

---

## Out of Scope (deferred to 008)

- Photoframe-side fade-in animation
- Photoframe reading the signal file for graceful exit (currently still
  uses kill -9 fallback)
- `/tmp/photoframe.ready` written by photoframe itself (007 polls for it
  but if 008 is not done, the timeout path will trigger; that's still safer
  than silent failure)
