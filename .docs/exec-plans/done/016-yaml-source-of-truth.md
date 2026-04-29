# 016 — Collapse config to a yaml-only source of truth

## Status: Planned 🟡

## Motivation

Plan 015 collapsed the L1 module-level globals into `BridgeConfig`,
but every `voiceBridge` knob still lives in **four places**:

| Layer | File | Role |
|-------|------|------|
| L1 — dataclass field defaults | [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) `BridgeConfig` lines 47–105 | "Last-resort" fallbacks (e.g. `search_timeout_sec: int = 90`, `search_hint: str = "好，我幫你查一下，請稍等。"`, `llm_system_prompt: str = "你是兔兔助理…"`) |
| L2 — default dict | [src/bridge/runtime_config.py](../../src/bridge/runtime_config.py) `DEFAULT_VOICEBRIDGE_CONFIG` lines 12–104 | Same ~30 keys as a nested dict; deep-merged into the user yaml inside `load_app_config()` |
| L3 — inline `.get(k, default)` | [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py) `build_bridge_config()` lines 161–217 | Re-reads the merged dict and falls back to *literals* / `BridgeConfig.<field>` (e.g. `routing.get("search_timeout_sec", BridgeConfig.search_timeout_sec)`, `audio.get("sample_rate", 16000)`) |
| L4 — user yaml | [config.yaml](../../config.yaml) lines 30–135 | The yaml the user actually edits — currently lists every key with the same literal as L1/L2 |

Net effect: **~30 keys × 3–4 copies ≈ 90 duplicated literals**.
Examples picked by the user:

- `search_timeout_sec` — yaml `90`, dict `90`, dataclass `90`, inline `BridgeConfig.search_timeout_sec`.
- `search_hint` — same string `"好，我幫你查一下，請稍等。"` in 4 places.
- `api_url` — `http://127.0.0.1:8000/zero-assistant` in 4 places.
- `llm_system` / `spoken_reply` — full prompt strings in yaml + dict + dataclass + inline fallback.
- `state_path` / `playback_device` / `llm_model` / etc. — same pattern.

Cross-file extras:

- `messageSource.path` (yaml line 27) and `voiceBridge.state_path`
  (yaml line 31) point at the same `data/demo_state.json` but are two
  independent yaml keys; UI reads the former in [src/ui/assistant_ui.py](../../src/ui/assistant_ui.py)
  line 342, the bridge reads the latter.
- `messageSource.poll_interval` is no longer read anywhere
  (grep confirms only the `path` line and the section header are
  referenced).

Because `load_app_config()` already deep-merges `DEFAULT_VOICEBRIDGE_CONFIG`
into the user yaml, the L3 inline fallbacks (`.get(k, …)`) are
**dead code** — the merged dict is always populated. The L1 dataclass
defaults are also dead: `grep -RIn 'BridgeConfig()' tests/` returns
zero hits, so no unit test instantiates a bare `BridgeConfig`.

This plan keeps **only L4 (yaml) as the runtime source of truth**.
L1/L2/L3 disappear; `BridgeConfig` keeps its dataclass shape (for type
hints + IDE autocomplete) but every field becomes required, and
`build_bridge_config()` switches to strict `dict[k]` subscripting that
fails fast with a friendly `ValueError` if the yaml is missing a key.

Out of scope:

- `display`/`colors`/`assets` blocks in `config.yaml` — already
  single-layer, no duplication.
- Provider URL strings (`model_url`, `tokens_url`) inside `stt`/`tts`
  providers — these are per-provider data, not duplication.
- `rabbitctl.sh` shell-level fallbacks (`兔兔助理`, `plughw:2,0`) —
  separate concern (CLI defaults vs runtime defaults).
- Remaining tech-debt items
  (`AssistRequest.language/source`, `_should_route_without_wake`
  length fallback, `DEFAULT_VOICE` typo).

---

## User decisions (locked)

| Question | Choice |
|---|---|
| Source of truth | **yaml only** (drop L1 + L2 + L3) |
| Missing-key policy | **fail-fast** — `ValueError("config.yaml missing voiceBridge.<dotted>")` |
| `messageSource.path` ↔ `voiceBridge.state_path` | **merge** — UI reads `voiceBridge.state_path`; whole `messageSource:` block dropped (`poll_interval` is dead) |
| `BridgeConfig` shape | **keep dataclass, drop all field defaults** — every field required, `BridgeConfig()` bare call becomes `TypeError` (acceptable; no test does so) |

---

## Pre-flight

- [ ] Confirm 015 has shipped: `git log --oneline | head -3` →
      expect `6042b71` at HEAD.
- [ ] Snapshot baseline tests: `.venv/bin/pytest -q` →
      expect **74 passed**.
- [ ] `git status -s` clean.

---

## Phase A — Drop the L2 dict layer

### Step 1 — Strip `DEFAULT_VOICEBRIDGE_CONFIG` + `_deep_merge`

In [src/bridge/runtime_config.py](../../src/bridge/runtime_config.py):

- Delete `DEFAULT_VOICEBRIDGE_CONFIG` (lines 12–104).
- Delete `_deep_merge()` (lines 107–114).
- Rewrite `load_app_config()`:

  ```python
  def load_app_config(config_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
      path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
      if not path.is_absolute():
          path = PROJECT_DIR / path
      if not path.exists():
          raise FileNotFoundError(f"config.yaml not found at {path}")
      with path.open("r", encoding="utf-8") as fh:
          loaded = yaml.safe_load(fh) or {}
      if "voiceBridge" not in loaded:
          raise ValueError(f"{path} is missing the top-level 'voiceBridge' key")
      return path, loaded
  ```

- Keep `get_selected_provider()` unchanged (already strict — raises
  `ValueError` on missing `active`/provider name).

### Step 2 — Helper for friendly missing-key errors

Add a tiny helper at the top of `runtime_config.py`:

```python
def require_key(d: dict[str, Any], dotted: str) -> Any:
    """Walk `dotted` (e.g. 'voiceBridge.routing.api_url') and raise
    ValueError if any segment is absent."""
    cur: Any = d
    for i, seg in enumerate(dotted.split(".")):
        if not isinstance(cur, dict) or seg not in cur:
            raise ValueError(f"config.yaml missing key: {dotted}")
        cur = cur[seg]
    return cur
```

Used by `build_bridge_config()` only when we want a custom error
message; bulk reads continue to use plain subscripting wrapped in a
single `try/except KeyError` (Step 4).

---

## Phase B — Strict `BridgeConfig` + `build_bridge_config` (depends on A)

### Step 3 — Remove all `BridgeConfig` field defaults

In [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
`@dataclass class BridgeConfig:` (lines 47–105):

- Remove every default value / `field(default_factory=...)`.
- Keep type annotations; reorder so all fields are bare annotations
  (no defaulted fields can precede non-defaulted ones).
- Remove the docstring sentence about "Defaults below are last-resort
  fallbacks…"; replace with: "All fields are required and populated
  by `build_bridge_config()` from the merged yaml."

Resulting fields (alphabetised for review only — actual order can stay
as-is):

```python
@dataclass
class BridgeConfig:
    api_url: str
    auto_route_cooldown_sec: float
    direct_max_tokens: int
    frame_ms: int
    input_device: Optional[int]
    llm_model: str
    llm_system_prompt: str
    padding_ms: int
    pending_wake_timeout_sec: float
    playback_device: str
    rewrite_search_reply_for_speech: bool
    sample_rate: int
    search_hint: str
    search_reply_max_tokens: int
    search_timeout_sec: int
    sentence_endings: str
    silero_model_path: Path
    silero_model_url: str
    silero_silence_threshold: float
    silero_speech_threshold: float
    silero_vote_required: int
    silero_vote_window: int
    spoken_reply_max_input_chars: int
    spoken_reply_prompt: str
    spoken_reply_timeout_sec: int
    state_path: Path
    stream_chunk_chars: int
    stream_max_tokens: int
    stt_provider_config: dict[str, Any]
    stt_provider_type: str
    trim_chars: str
    tts_provider_config: dict[str, Any]
    tts_provider_type: str
    wake_variants: tuple[str, ...]
    webrtc_aggressiveness: int
```

(35 fields. No defaults.)

### Step 4 — Strict `build_bridge_config()` body

Rewrite the function body so every read is a direct subscript inside a
single `try/except`:

```python
def build_bridge_config(voice_config: dict[str, Any], args: argparse.Namespace) -> BridgeConfig:
    try:
        audio = voice_config["audio"]
        wake = voice_config["wake"]
        routing = voice_config["routing"]
        prompts = voice_config["prompts"]
        text_cfg = voice_config["text"]
        vad = voice_config["vad"]
        silero = vad["silero"]
        _, stt_provider = get_selected_provider(voice_config, "stt")
        _, tts_provider = get_selected_provider(voice_config, "tts")

        input_device = args.input_device if args.input_device is not None else audio["input_device"]
        playback_device = args.playback_device or audio["playback_device"]

        cfg = BridgeConfig(
            sample_rate=int(audio["sample_rate"]),
            frame_ms=int(audio["frame_ms"]),
            padding_ms=int(audio["padding_ms"]),
            input_device=input_device,
            playback_device=playback_device,
            pending_wake_timeout_sec=float(wake["follow_up_timeout_sec"]),
            auto_route_cooldown_sec=float(wake["auto_route_cooldown_sec"]),
            webrtc_aggressiveness=int(vad["webrtc_aggressiveness"]),
            silero_speech_threshold=float(silero["speech_threshold"]),
            silero_silence_threshold=float(silero["silence_threshold"]),
            silero_vote_window=int(silero["vote_window"]),
            silero_vote_required=int(silero["vote_required"]),
            search_timeout_sec=int(routing["search_timeout_sec"]),
            direct_max_tokens=int(routing["direct_max_tokens"]),
            stream_max_tokens=int(routing["stream_max_tokens"]),
            search_reply_max_tokens=int(routing["search_reply_max_tokens"]),
            rewrite_search_reply_for_speech=bool(routing["rewrite_search_reply_for_speech"]),
            spoken_reply_timeout_sec=int(routing["spoken_reply_timeout_sec"]),
            spoken_reply_max_input_chars=int(routing["spoken_reply_max_input_chars"]),
            search_hint=str(routing["search_hint"]),
            api_url=str(routing["api_url"]),
            llm_model=str(routing["llm_model"]),
            llm_system_prompt=str(prompts["llm_system"]),
            spoken_reply_prompt=str(prompts["spoken_reply"]),
            trim_chars=str(text_cfg["trim_chars"]),
            sentence_endings=str(text_cfg["sentence_endings"]),
            stream_chunk_chars=int(text_cfg["stream_chunk_chars"]),
            stt_provider_type=str(stt_provider["type"]),
            stt_provider_config={k: v for k, v in stt_provider.items() if k not in {"type", "name"}},
            tts_provider_type=str(tts_provider["type"]),
            tts_provider_config={k: v for k, v in tts_provider.items() if k not in {"type", "name"}},
            wake_variants=tuple(wake["variants"]),
            state_path=resolve_project_path(voice_config["state_path"]),
            silero_model_path=resolve_project_path(silero["model_path"]),
            silero_model_url=str(silero["model_url"]),
        )
    except KeyError as exc:
        raise ValueError(
            f"config.yaml missing voiceBridge key: {exc.args[0]!r}"
        ) from exc

    if args.wake:
        cfg.wake_variants = tuple(dict.fromkeys((args.wake, *cfg.wake_variants)))
    return cfg
```

Notes:

- `voice_config["state_path"]` (not `voice_config.get(...)`) — fails
  fast if user yaml drops it.
- `audio["input_device"]` may legitimately be `null` (yaml line 35) →
  Python `None`. CLI override still wins.
- `KeyError → ValueError` swap lets callers catch a single exception
  type with a friendly message.

### Step 5 — `main()` cleanup

Currently `main()` reads `voice_config = app_config.get("voiceBridge", {})`.
Switch to direct subscript: `app_config["voiceBridge"]` (already
guaranteed by the strict `load_app_config()` from Step 1).

`build_arg_parser()` already takes `default_playback`/`default_wake`
kwargs (015). No change needed — `main()` continues to pass
`audio["playback_device"]` and `wake["primary"]` from the strict dict.

---

## Phase C — UI + yaml cleanup (parallel with B)

### Step 6 — UI switch

In [src/ui/assistant_ui.py](../../src/ui/assistant_ui.py) line 342:

```diff
-    feed = JsonStateFeed(PROJECT_DIR / cfg["messageSource"]["path"])
+    feed = JsonStateFeed(PROJECT_DIR / cfg["voiceBridge"]["state_path"])
```

### Step 7 — yaml drop `messageSource:`

In [config.yaml](../../config.yaml) lines 26–28: delete the entire
`messageSource:` block (3 lines including blank).

Verification grep `messageSource|message_source|poll_interval`
expected to return zero hits after the edits.

---

## Phase D — Tests (depends on A/B)

### Step 8 — Full-config helper for partial-yaml tests

In [tests/test_runtime_config.py](../../tests/test_runtime_config.py):

```python
import shutil

PROJECT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"

def _write_full_config(tmp_path: Path, **dotted_overrides) -> Path:
    """Copy the project's config.yaml into tmp_path and apply
    ``dotted.key=value`` overrides via in-memory dict mutation, then
    dump back to yaml. Lets each test focus on the keys it cares
    about while keeping the strict yaml requirement satisfied."""
    import yaml as _yaml
    target = tmp_path / "config.yaml"
    data = _yaml.safe_load(PROJECT_CONFIG.read_text(encoding="utf-8")) or {}
    for dotted, value in dotted_overrides.items():
        cur = data
        parts = dotted.split(".")
        for seg in parts[:-1]:
            cur = cur.setdefault(seg, {})
        cur[parts[-1]] = value
    target.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target
```

### Step 9 — Rewrite the two existing build-config tests

Both `test_build_bridge_config_uses_active_provider_selection` and
`test_build_bridge_config_populates_runtime_strings` currently write a
*partial* yaml. Switch them to call `_write_full_config(tmp_path,
**{"voiceBridge.audio.playback_device": "plughw:9,0", ...})` so the
strict loader is happy. Behaviour assertions stay identical.

### Step 10 — New missing-key test

Add:

```python
def test_load_app_config_strict_missing_key_raises(tmp_path):
    config_path = _write_full_config(tmp_path)
    # Drop a required key by re-loading and re-dumping
    import yaml as _yaml
    data = _yaml.safe_load(config_path.read_text())
    del data["voiceBridge"]["routing"]["api_url"]
    config_path.write_text(_yaml.safe_dump(data, allow_unicode=True))

    _, app_config = load_app_config(config_path)
    args = argparse.Namespace(config=str(config_path), input_device=None,
                              playback_device=None, wake=None)
    with pytest.raises(ValueError, match="api_url"):
        build_bridge_config(app_config["voiceBridge"], args)
```

(Add `import pytest` at the top of the file.)

### Step 11 — Update `test_update_state_round_trip`

Unchanged (it does not touch `BridgeConfig`).

---

## Phase E — Verification

- [ ] `.venv/bin/pytest -q` → expect **75 passed** (74 baseline + 1 new).
- [ ] Bare-instantiation guard:
      `python -c "from src.bridge.voice_bridge import BridgeConfig; BridgeConfig()"`
      → expect `TypeError`.
- [ ] Grep sweeps (each must return 0 hits):
  - `grep -RIn 'DEFAULT_VOICEBRIDGE_CONFIG' src/ tests/`
  - `grep -RIn 'messageSource' src/ tests/ config.yaml`
  - `grep -RIn 'BridgeConfig\\.' src/`  (no more `routing.get(..., BridgeConfig.x)`)
  - `grep -RIn '_deep_merge' src/ tests/`
- [ ] Import smoke:
      `python -c "from src.bridge.runtime_config import load_app_config; print(load_app_config()[1].keys())"`
      → expect `dict_keys(['display', 'colors', 'assets', 'voiceBridge'])`.

---

## Phase F — Live run gate (await user OK)

- [ ] `bash rabbitctl.sh restart`.
- [ ] Confirm 3 PIDs (api / ui / voice_bridge) up via the script's
      output.
- [ ] `tail -20 logs/voice_bridge.log` — no `ValueError` / no missing
      key.
- [ ] Optional: `curl -X POST http://127.0.0.1:8000/zero-assistant
      -H 'content-type: application/json' -d '{"text":"你好"}'`
      → expect 200 + non-empty reply.
- [ ] Optional: mic sanity ("兔兔助理 現在幾點") → bunny reacts +
      `data/demo_state.json` updates.

---

## Phase G — Docs + commit + push (await user OK)

- [ ] Update `.docs/tech-debt.md`: add Resolved row referencing 016
      above the 015 row.
- [ ] Update `.docs/context.md`: append `**016** ✅` block summarising
      the collapse.
- [ ] Update `PLAN.md`: add row 17 ("Collapse config to yaml-only
      source of truth (exec-plan 016) | ✅ Done") and extend the
      archived list with `016 (yaml-source-of-truth)`.
- [ ] `mv .docs/exec-plans/016-yaml-source-of-truth.md
      .docs/exec-plans/done/`.
- [ ] `git add -A && git commit -m "refactor(016): collapse config
      to yaml-only source of truth"` (full body drafted at commit
      time, mirroring the 015 commit format).
- [ ] `git push origin main`.

---

## Verification checklist (final)

1. `pytest -q` → 75 passed.
2. `BridgeConfig()` bare → `TypeError`.
3. All four greps in Phase E return 0 hits.
4. Live restart clean; 3 PIDs up; log silent.
5. (optional) curl + mic round-trip OK.

## Decisions & risks

- **Decision**: dataclass shape kept (Option A from the question
  flow) so type hints + IDE autocomplete + `self.cfg.<field>` access
  pattern survive untouched. Trade-off: any test that wants a
  `BridgeConfig` must use the full-yaml fixture.
- **Decision**: `messageSource:` block dropped wholesale.
  `messageSource.poll_interval` is dead (no readers); `messageSource.path`
  collapsed into `voiceBridge.state_path`.
- **Risk**: a forgotten yaml key only surfaces when
  `build_bridge_config()` runs. Mitigation: the missing-key test
  (Step 10) plus the Phase F live restart catch this before commit.
- **Risk**: provider-config dicts (`stt_provider_config`,
  `tts_provider_config`) currently spread `provider.items()`; if a
  user's provider block is missing required keys (e.g. Sherpa
  `model_path`), the failure happens later inside the provider
  constructor. Out of scope here — providers already have their own
  validation.
