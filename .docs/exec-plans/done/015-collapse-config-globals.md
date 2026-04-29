# 015 — Collapse module-level config globals into `BridgeConfig`

## Status: Planned 🟡

## Motivation

Three layers describe the *same* runtime config today:

| Layer | File | Role |
|-------|------|------|
| L1 — module globals | [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) lines 46–71 | 17 hard-coded fallback constants (`STATE_PATH`, `DEFAULT_WAKE`, `LLM_MODEL`, `API_URL`, `SEARCH_TIMEOUT_SEC`, `LLM_SYSTEM_PROMPT`, …) |
| L2 — default dict | [src/bridge/runtime_config.py](../../src/bridge/runtime_config.py) `DEFAULT_VOICEBRIDGE_CONFIG` lines 12–125 | The same 17 values, expressed as a nested dict, deep-merged into the loaded yaml |
| L3 — user yaml | [config.yaml](../../config.yaml) lines 30–135 `voiceBridge:` | The yaml the user actually edits |

L2 already deep-merges into L3 inside `load_app_config()`, so by the
time `apply_runtime_config()` runs the merged dict is *guaranteed* to
contain every key. The 35-line `apply_runtime_config()` body
(`voice_bridge.py` lines 151–185) only exists to **mutate the L1
globals** so that the few code paths that still read globals
(`update_state` → `STATE_PATH`; `VoiceBridge._stream_chat` →
`LLM_MODEL` / `LLM_SYSTEM_PROMPT`; etc.) see the merged value. Then
`build_bridge_config()` (lines 188–229) reads the *same* merged dict
**again** with `routing.get("key", GLOBAL)` to populate the
`BridgeConfig` dataclass — a third copy of every key.

Net effect:

- Every config key has to be touched in **3 places** to be added or
  renamed.
- 6 settings that *are* runtime-configurable (`LLM_MODEL`,
  `LLM_SYSTEM_PROMPT`, `SPOKEN_REPLY_PROMPT`, `TRIM_CHARS`,
  `SENTENCE_ENDINGS`, `STREAM_CHUNK_CHARS`) live as globals **only**
  and never made it onto `BridgeConfig` — this is the entire reason
  `apply_runtime_config()` exists.
- The yaml block `voiceBridge.text.search_tokens` is dead config left
  over from 014 (no one reads it any more).

This plan eliminates L1 entirely, making `BridgeConfig` the single
runtime-config object. `DEFAULT_VOICEBRIDGE_CONFIG` (L2) stays as the
deep-merge fallback so a partial user yaml still boots.

Out of scope:

- Redesigning `runtime_config.DEFAULT_VOICEBRIDGE_CONFIG` itself — it
  remains the canonical default source. (The "L2 also disappears"
  variant from chat is deferred — value/risk ratio worse.)
- `get_selected_provider()` — already clean.
- Remaining tech-debt items
  (`AssistRequest.language/source`, `_should_route_without_wake`
  length fallback, `DEFAULT_VOICE` typo).
- `config.yaml` schema rename / restructuring.

---

## Pre-flight

- [ ] Confirm 014 has shipped: `git log --oneline | grep 014` → expect
      `6ace3c4`.
- [ ] Snapshot baseline tests: `.venv/bin/pytest -q` → expect
      **72 passed**.
- [ ] `git status -s` clean.

---

## Phase A — Extend `BridgeConfig` to cover every runtime-mutable knob

### Step 1 — Add the missing fields to `BridgeConfig`

Inside `voice_bridge.py` `@dataclass class BridgeConfig:` (lines 74–105)
add the 9 fields that today live only as module globals:

```python
state_path: Path = field(default_factory=lambda: STATE_PATH)
silero_model_path: Path = field(default_factory=lambda: SILERO_MODEL_PATH)
silero_model_url: str = SILERO_MODEL_URL
llm_model: str = LLM_MODEL
llm_system_prompt: str = LLM_SYSTEM_PROMPT
spoken_reply_prompt: str = SPOKEN_REPLY_PROMPT
trim_chars: str = TRIM_CHARS
sentence_endings: str = SENTENCE_ENDINGS
stream_chunk_chars: int = STREAM_CHUNK_CHARS
```

Notes:

- Use `field(default_factory=lambda: …)` for the two `Path` fields
  because `Path` instances are mutable and dataclass forbids mutable
  defaults at class scope.
- Defaults still reference the L1 globals on purpose — they get
  removed in Phase D, so this step is a no-op behaviourally and keeps
  the diff bisectable.
- Field order: append at the end of the existing dataclass body so
  positional construction (none in the codebase, but defensive) is
  unaffected.

---

## Phase B — Populate the new fields in `build_bridge_config()` (depends on A)

### Step 2 — Read every key from the merged dict, not from globals

In `build_bridge_config()` (lines 188–229), append after the existing
`wake_variants=…` line (and before the closing `)`):

```python
state_path=resolve_project_path(voice_config.get("state_path", "data/demo_state.json")),
silero_model_path=resolve_project_path(silero.get("model_path", "models/silero_vad.onnx")),
silero_model_url=str(silero.get("model_url", BridgeConfig.silero_model_url)),
llm_model=str(routing.get("llm_model", BridgeConfig.llm_model)),
llm_system_prompt=str(prompts.get("llm_system", BridgeConfig.llm_system_prompt)),
spoken_reply_prompt=str(prompts.get("spoken_reply", BridgeConfig.spoken_reply_prompt)),
trim_chars=str(text_cfg.get("trim_chars", BridgeConfig.trim_chars)),
sentence_endings=str(text_cfg.get("sentence_endings", BridgeConfig.sentence_endings)),
stream_chunk_chars=int(text_cfg.get("stream_chunk_chars", BridgeConfig.stream_chunk_chars)),
```

Also add the section lookups at the top of the function:

```python
prompts = voice_config.get("prompts", {})
text_cfg = voice_config.get("text", {})
```

(They are currently only fetched in `apply_runtime_config()`.)

Behaviour preserved: `runtime_config.load_app_config()` already
deep-merges `DEFAULT_VOICEBRIDGE_CONFIG`, so `.get(key, …)` will always
hit the merged value; the literal/dataclass fallback only kicks in if
the merged dict is somehow missing the key (defensive).

---

## Phase C — Switch readers from globals to `self.cfg` (depends on B)

### Step 3 — `VoiceBridge` instance methods

Replace inside `VoiceBridge` body:

| Current (global) | New (instance) | Locations |
|---|---|---|
| `LLM_MODEL` | `self.cfg.llm_model` | lines 552, 580, 720 |
| `LLM_SYSTEM_PROMPT` | `self.cfg.llm_system_prompt` | lines 556, 584 |
| `SPOKEN_REPLY_PROMPT` | `self.cfg.spoken_reply_prompt` | line 722 |
| `TRIM_CHARS` | `self.cfg.trim_chars` | line 304 |
| `SENTENCE_ENDINGS` | `self.cfg.sentence_endings` | line 645 |
| `STREAM_CHUNK_CHARS` | `self.cfg.stream_chunk_chars` | lines 652, 653, 654 |
| `SILERO_MODEL_PATH` | `self.cfg.silero_model_path` | line 247 |
| `SILERO_MODEL_URL` | `self.cfg.silero_model_url` | line 247 |

### Step 4 — `update_state()` is module-level → take an explicit path

`update_state()` (lines 745–763) currently reads `STATE_PATH` from
module scope. It is called from three places:

- `VoiceBridge._capture_utterance` / `run` / `_handle_command` (always
  inside an instance — has `self.cfg.state_path`).
- Possibly imported by the UI? Check with grep first
  (`grep -RIn 'from src.bridge.voice_bridge import update_state'`) —
  expectation: not imported elsewhere; only used inside this module.

Refactor option (chosen):

```python
def update_state(state_path: Path, phase: str, *, user_text=None, assistant_text=None) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    ...
```

…and update every call site to `update_state(self.cfg.state_path, …)`.
Pure mechanical — about 8 call sites; verify with grep.

If grep shows external importers, keep a thin wrapper:

```python
def update_state_default(phase, **kw):
    update_state(STATE_PATH, phase, **kw)
```

(don’t expect this to be needed; `update_state` is internal).

### Step 5 — `build_arg_parser()` defaults

Lines 780–783 reference `DEFAULT_PLAYBACK` / `DEFAULT_WAKE` for argparse
help text + defaults. These must keep working **before**
`build_bridge_config()` runs (argparse runs first in `main()`). Two
choices:

(a) Have `build_arg_parser()` accept the values as parameters:

```python
def build_arg_parser(default_config_path, default_input_device, *,
                    default_playback: str, default_wake: str) -> argparse.ArgumentParser:
    ...
```

…then call it with values pulled from the merged `voice_config` (which
is loaded *before* full args parsing in the existing `main()`). The
`audio.playback_device` and `wake.primary` keys are guaranteed present
thanks to the deep-merge.

(b) Keep two tiny `_DEFAULT_PLAYBACK_FALLBACK` / `_DEFAULT_WAKE_FALLBACK`
constants as **argparse-only** strings.

**Pick (a)** — it eliminates the last two L1 globals cleanly.

Updated `main()`:

```python
config_path, app_config = load_app_config(pre_args.config)
voice_config = app_config.get("voiceBridge", {})
audio_cfg = voice_config.get("audio", {})
wake_cfg = voice_config.get("wake", {})
args = build_arg_parser(
    config_path,
    audio_cfg.get("input_device"),
    default_playback=str(audio_cfg.get("playback_device", "plughw:2,0")),
    default_wake=str(wake_cfg.get("primary", "兔兔助理")),
).parse_args()
client = OpenAI()
cfg = build_bridge_config(voice_config, args)
```

Note: the `apply_runtime_config(app_config)` call **disappears** from
`main()` — see Phase D Step 7.

---

## Phase D — Delete L1 (depends on C)

### Step 6 — Remove module-level globals

Delete from `voice_bridge.py`:

- The 17 module-level constants block (lines 46–71): `STATE_PATH`,
  `SILERO_MODEL_PATH`, `SILERO_MODEL_URL`, `DEFAULT_WAKE`,
  `DEFAULT_PLAYBACK`, `LLM_MODEL`, `API_URL`, `SEARCH_TIMEOUT_SEC`,
  `DIRECT_MAX_TOKENS`, `STREAM_MAX_TOKENS`, `SEARCH_REPLY_MAX_TOKENS`,
  `TRIM_CHARS`, `SENTENCE_ENDINGS`, `STREAM_CHUNK_CHARS`,
  `LLM_SYSTEM_PROMPT`, `SPOKEN_REPLY_PROMPT`, `SEARCH_HINT`.
- Keep `BASE_DIR` and `DEFAULT_CONFIG_PATH` — both are needed by
  `runtime_config` semantics + argparse pre-parser before any config
  is loaded.

Migration shim for `BridgeConfig` defaults: replace the `default_factory`
fallbacks added in Step 1 with literal defaults (now that the L1
globals are gone):

```python
state_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "demo_state.json")
silero_model_path: Path = field(default_factory=lambda: BASE_DIR / "models" / "silero_vad.onnx")
silero_model_url: str = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
llm_model: str = "gpt-4o-mini"
llm_system_prompt: str = (
    "你是兔兔助理，一個友善的繁體中文語音助理。"
    "請用簡短的中文回答，不超過 30 個字，不使用 Markdown。"
)
spoken_reply_prompt: str = (
    "你要把搜尋結果改寫成適合語音播報的繁體中文。"
    "規則：只保留重點、1到2句、不要網址、不要 Markdown、不要括號引用、"
    "不要條列、不要唸出奇怪符號，盡量口語自然。"
)
trim_chars: str = " ，、。!?~'\""
sentence_endings: str = "，,。！？!?；;：:\n"
stream_chunk_chars: int = 24
```

These **duplicate** `DEFAULT_VOICEBRIDGE_CONFIG` (L2). That is the
intended trade — dataclass defaults exist purely so
`BridgeConfig()` is instantiable in unit tests without a yaml file.
The runtime path always goes through `load_app_config()` which feeds
L2 → L3 → `build_bridge_config()`, so the dataclass defaults are
**only** the fallback-of-last-resort.

(Future plan 016 could collapse L1-defaults-in-dataclass + L2 into a
single source if it becomes painful; not worth it now.)

### Step 7 — Delete `apply_runtime_config()`

Remove the entire function (lines 151–185) and its call site in
`main()` (line 798: `voice_config = apply_runtime_config(app_config)`).
Replace the call site with:

```python
voice_config = app_config.get("voiceBridge", {})
```

### Step 8 — Drop dead yaml: `voiceBridge.text.search_tokens`

Edit [config.yaml](../../config.yaml) and remove lines 81–99 (the
`search_tokens:` list under `voiceBridge.text`). Also drop the same
list from [src/bridge/runtime_config.py](../../src/bridge/runtime_config.py)
`DEFAULT_VOICEBRIDGE_CONFIG["text"]` (lines 65–84).

After 014 the canonical token list lives in
`src/api/skills/tokens.SEARCH_TOKENS` and nothing reads the yaml copy
any more.

---

## Phase E — Tests (depends on D)

### Step 9 — Update `tests/test_runtime_config.py`

The existing test
`test_build_bridge_config_uses_active_provider_selection` imports
`apply_runtime_config` (line 13) and calls it (line 54). After Step 7
the symbol is gone. Two changes:

```python
# line 13
from src.bridge.voice_bridge import build_bridge_config

# line 54 — delete the apply_runtime_config call entirely; just take
# the merged voiceBridge subtree directly
voice_config = app_config["voiceBridge"]
```

The rest of the test (assertions on `cfg.*`) is untouched; the new
`BridgeConfig` fields populated in Phase B mean those assertions still
pass.

### Step 10 — Add coverage for the new fields

In the same file (or a new lightweight test), add:

```python
def test_build_bridge_config_populates_runtime_strings(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
voiceBridge:
  routing:
    llm_model: gpt-4-test
  prompts:
    llm_system: "test system prompt"
    spoken_reply: "test spoken prompt"
  text:
    trim_chars: "_"
    sentence_endings: "."
    stream_chunk_chars: 7
""",
        encoding="utf-8",
    )
    _, app_config = load_app_config(config_path)
    args = argparse.Namespace(
        config=str(config_path), input_device=None,
        playback_device=None, wake=None,
    )
    cfg = build_bridge_config(app_config["voiceBridge"], args)
    assert cfg.llm_model == "gpt-4-test"
    assert cfg.llm_system_prompt == "test system prompt"
    assert cfg.spoken_reply_prompt == "test spoken prompt"
    assert cfg.trim_chars == "_"
    assert cfg.sentence_endings == "."
    assert cfg.stream_chunk_chars == 7
```

This locks the L2→`BridgeConfig` plumbing.

### Step 11 — Add a regression test for `update_state()`

Quick sanity check that `update_state(tmp_path/"state.json", "idle")`
writes the file. Lives in `tests/test_runtime_config.py` (or a new
`tests/test_state_io.py` — pick whichever gives the leanest diff).

---

## Phase F — Verification (depends on E)

### Step 12 — Test suite

```
.venv/bin/pytest -q
```

Expected: **74 passed** (72 baseline + 2 new tests). If the existing
`test_build_bridge_config_uses_active_provider_selection` count
changes due to refactoring of its body, adjust accordingly.

### Step 13 — Import smoke

```
.venv/bin/python -c "
from src.bridge.voice_bridge import BridgeConfig, build_bridge_config, VoiceBridge
import src.bridge.voice_bridge as vb
assert not hasattr(vb, 'apply_runtime_config'), 'apply_runtime_config should be gone'
assert not hasattr(vb, 'STATE_PATH'), 'STATE_PATH global should be gone'
assert not hasattr(vb, 'LLM_MODEL'), 'LLM_MODEL global should be gone'
print('ok', list(BridgeConfig.__dataclass_fields__).count('llm_model'))
"
```

### Step 14 — Grep sweep

```
grep -RIn '\b(STATE_PATH|SILERO_MODEL_PATH|SILERO_MODEL_URL|DEFAULT_WAKE|DEFAULT_PLAYBACK|LLM_MODEL|API_URL|SEARCH_TIMEOUT_SEC|DIRECT_MAX_TOKENS|STREAM_MAX_TOKENS|SEARCH_REPLY_MAX_TOKENS|TRIM_CHARS|SENTENCE_ENDINGS|STREAM_CHUNK_CHARS|LLM_SYSTEM_PROMPT|SPOKEN_REPLY_PROMPT|SEARCH_HINT)\b' src/ tests/
```

Expect:

- Zero hits in `src/bridge/voice_bridge.py` (all moved to dataclass
  field names like `llm_model`).
- Hits in `src/bridge/runtime_config.py` only as **dict keys** in
  `DEFAULT_VOICEBRIDGE_CONFIG` (lower-case `llm_model:` etc.) — those
  belong to L2 and stay.
- Hits in tests only as `cfg.llm_model` style attribute access.

```
grep -RIn 'apply_runtime_config' src/ tests/
```

Expect: **zero matches**.

```
grep -RIn 'search_tokens' src/ tests/ config.yaml
```

Expect: **zero matches** (014 deleted the helper; this plan deletes
the dead yaml block).

### Step 15 — Live verification (await user OK)

```
./rabbitctl.sh restart
```

Then four-call smoke:

```
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"打開相框"}' | jq             # local-skill
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"切回兔兔"}' | jq             # local-skill
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"你好"}' | jq                # fallback-openai
curl -s -X POST localhost:8000/zero-assistant -H 'Content-Type: application/json' \
     -d '{"text":"幫我查台北天氣"}' | jq      # openai-websearch
```

Plus mic-driven sanity:

- "兔兔助理 你好" — fallback-openai stream
- "兔兔助理 幫我查台北天氣" — websearch (search hint must still play
  before the result, which exercises `self.cfg.search_hint` plumbing)
- "兔兔助理 切回兔兔" — local-skill

The mic test specifically guards against the `update_state()` /
`STATE_PATH` refactor: the bunny UI polls `data/demo_state.json`, so if
the path plumbing broke the bunny mouth would stop animating.

---

## Phase G — Wrap-up (requires user approval at each gate)

### Step 16 — Docs

- `.docs/tech-debt.md`: add a Resolved row referencing 015 for the
  L1/L2/L3 config triplication.
- `.docs/context.md`: append `015 ✅` notes (mirror the 014 entry
  style; mention the dead `text.search_tokens` cleanup).
- `PLAN.md`: add Phase 16 = 015 ✅ row; add 015 to the archived list.

### Step 17 — Archive plan

```
git mv .docs/exec-plans/015-collapse-config-globals.md .docs/exec-plans/done/
```

### Step 18 — Commit (await user OK)

Single commit:

```
refactor(015): collapse module-level config globals into BridgeConfig

- BridgeConfig now owns every runtime-mutable knob (state_path,
  silero_model_path/url, llm_model, llm_system_prompt,
  spoken_reply_prompt, trim_chars, sentence_endings, stream_chunk_chars
  added to the dataclass).
- build_bridge_config() reads them all from the deep-merged voice_config
  dict, so the merged-config → dataclass plumbing is now the single
  source of runtime truth.
- apply_runtime_config() and the 17 module-level fallback globals
  (STATE_PATH, DEFAULT_WAKE, LLM_MODEL, API_URL, SEARCH_TIMEOUT_SEC,
  ...) are deleted. update_state() now takes the path explicitly.
- build_arg_parser() now receives default_playback / default_wake from
  main() so the argparse layer no longer needs the L1 globals.
- config.yaml + runtime_config.DEFAULT_VOICEBRIDGE_CONFIG: drop the dead
  voiceBridge.text.search_tokens block (014 made it a no-op).
- tests/test_runtime_config.py: drop the apply_runtime_config import,
  read voiceBridge from app_config directly, add a coverage test for
  the new BridgeConfig fields plus an update_state() round-trip.

No behaviour change. pytest 74 passed. Live curl 4/4 + mic sanity OK.
```

### Step 19 — Push (await user OK)

`git push origin main` only after explicit approval.

---

## Relevant files

- `src/bridge/voice_bridge.py` — the bulk of the change: `BridgeConfig`
  gains 9 fields, `apply_runtime_config()` deleted, 17 globals deleted,
  `update_state()` takes a path, `build_arg_parser()` takes defaults.
- `src/bridge/runtime_config.py` — drop `DEFAULT_VOICEBRIDGE_CONFIG["text"]["search_tokens"]`
  list. Otherwise unchanged.
- `config.yaml` — drop the `voiceBridge.text.search_tokens` block.
- `tests/test_runtime_config.py` — repoint imports, add 2 tests.

## Risk + mitigation

- **`update_state()` signature change** breaks any external importer.
  Step 4 grep covers this; current expectation is zero importers.
- **`BridgeConfig` defaults duplicating `DEFAULT_VOICEBRIDGE_CONFIG`**
  is intentional but leaves L2 as the second source-of-truth.
  Acknowledged trade; flagged for a hypothetical 016. Mitigated by:
  the dataclass defaults are only used when constructing `BridgeConfig()`
  with no yaml, which only happens in unit tests.
- **`SEARCH_HINT` global removal** — only read inside
  `build_bridge_config()` (line 220) via `routing.get("search_hint",
  SEARCH_HINT)` and inside `VoiceBridge` via `self.cfg.search_hint`
  (line 356). The latter already uses the dataclass; the former gets
  swapped to `BridgeConfig.search_hint` as its dataclass-default
  fallback.
- **Bisectability**: Phase A keeps the globals in place as the
  `default_factory` source. Phase B–C make instances rely on
  `self.cfg.*`. Only Phase D actually deletes the globals. So if
  anything regresses, `git bisect` lands inside one specific phase.
