# 008 — Photoframe-side Smooth Transitions

## Status: Planned 🟡 (depends on 007 completed first)

## Motivation

After 007, voiceassist correctly routes "打開相框 / 打開相簿" via the new
skill dispatcher and the bunny UI fades out gracefully. But the photoframe
side is still abrupt:

- Photoframe pops in instantly with no fade-in (asymmetric to bunny's fade-out)
- Photoframe is killed via `kill -9` when switching back to bunny — risk of
  corrupted state, half-saved playlists, no chance to release the framebuffer
- `/tmp/photoframe.ready` (used by 007 to detect launch failure) is currently
  faked by the timeout path; photoframe itself doesn't write it

This plan adds three small, low-risk changes to `~/workspace/photoframe/`
to make the bunny ↔ photoframe transition feel like one app.

---

## Pre-flight (manual, by user)

```bash
cp -r ~/workspace/photoframe ~/workspace/photoframe.bak.$(date +%Y%m%d)
```

Photoframe is NOT a git repo and NOT a submodule of voiceassist. Backup
required before edits.

Optionally: turn it into a local git repo before edits so we can diff:
```bash
cd ~/workspace/photoframe && git init && git add -A && git commit -m "snapshot before voiceassist 008 edits"
```

---

## Action Items

### Step 1 — Fade-in on launch

- [ ] In `~/workspace/photoframe/main.py`:
  - Set `Window.opacity = 0` before `App.run()`
  - In `on_start()` (or via `Clock.schedule_once`), animate
    `Window.opacity` 0 → 1 over 0.4s
  - Match the timing constant used by bunny fade-out (007 step 5)

### Step 2 — Background signal poller

- [ ] Add `~/workspace/photoframe/services/voiceassist_signal.py`:
  ```python
  import json, time, threading
  from pathlib import Path

  SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")
  POLL_INTERVAL = 0.25

  def start(on_exit_request):
      def loop():
          while True:
              try:
                  if SIGNAL_PATH.exists():
                      data = json.loads(SIGNAL_PATH.read_text())
                      if data.get("photoframe_should_exit"):
                          on_exit_request()
                          return
              except Exception:
                  pass
              time.sleep(POLL_INTERVAL)
      t = threading.Thread(target=loop, daemon=True)
      t.start()
  ```

- [ ] In `main.py`, on `on_start()`:
  ```python
  from services.voiceassist_signal import start as start_signal
  def graceful_exit():
      # animate opacity 1 → 0 over 0.4s, then App.stop()
      ...
  start_signal(graceful_exit)
  ```

### Step 3 — Ready file

- [ ] In `main.py` `on_start()` after Window is shown:
  ```python
  Path("/tmp/photoframe.ready").touch()
  ```
- [ ] On graceful exit, remove it:
  ```python
  Path("/tmp/photoframe.ready").unlink(missing_ok=True)
  ```

### Step 4 — Voiceassist side cleanup (small)

- [ ] In `src/api/skills/open_bunny.py`: instead of `kill -9` photoframe,
      first write `photoframe_should_exit=true` to signal, sleep 0.6s,
      THEN kill as fallback
- [ ] In `src/api/skills/open_photoframe.py`: drop the "1.0s timeout fake
      ready" path — now photoframe writes the real ready file

### Step 5 — Docs / tests

- [ ] Update `.docs/product-specs/local-commands.md` — document IPC contract
      between voiceassist and photoframe via `/tmp/voiceassist_signal.json`
- [ ] Update `.docs/skill.md` — add "External app contract" subsection
- [ ] Add a test in `tests/test_skills.py` that mocks the signal file
      and asserts `open_bunny.run()` writes `photoframe_should_exit=true`
      before killing

---

## Acceptance Criteria

- [ ] Saying "打開相框": bunny fades out (0.4s) → photoframe fades in (0.4s),
      no flicker, no black flash
- [ ] Saying "切回兔兔": photoframe fades out (0.4s) → bunny fades in;
      photoframe exits cleanly (no `kill -9` in normal flow); checking
      photoframe log shows `graceful exit via signal`
- [ ] `/tmp/photoframe.ready` exists exactly while photoframe is running
- [ ] If photoframe crashes during launch (e.g. kivy missing), ready file
      never appears → voiceassist returns truthful failure message within 1.5s
- [ ] All pytest tests pass
- [ ] Commit msg: `feat(008): smooth photoframe transitions + signal-based exit`

---

## Rollback Plan

If 008 breaks photoframe:

1. `cd ~/workspace/photoframe && git checkout .` (if step 0 git init was done)
   OR
2. `rm -rf ~/workspace/photoframe && cp -r ~/workspace/photoframe.bak.<date> ~/workspace/photoframe`
3. In voiceassist: revert step 4 (re-enable kill -9 path)

---

## Out of Scope

- Slideshow transitions inside photoframe (already exists)
- Replacing kivy with another UI framework
- Persisting playlist / setup state across the bunny↔photoframe transition
- Photoframe ↔ voiceassist bidirectional state sync (only one direction:
  voiceassist → photoframe via signal file)

---

## Dependencies & Risks

- **Depends on 007** — without the new skill dispatcher writing the signal
  file, none of these changes activate.
- **Risk**: photoframe is on Raspberry Pi system Python; daemon thread may
  fight with Kivy's own event loop. Mitigation: poll interval 0.25s (gentle),
  daemon=True so process exits cleanly.
- **Risk**: if `/tmp` is mounted noexec or full, signal file writes fail.
  Mitigation: both sides catch exceptions silently; worst case behaviour
  degrades to today's kill -9 path.
