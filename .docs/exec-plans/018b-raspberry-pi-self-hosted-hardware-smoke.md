# 018B — Add Raspberry Pi Self-Hosted Hardware Smoke Workflow

## Status: Draft 🟡 (not started)

## Motivation

018A intentionally stops at a portable, GitHub-hosted baseline. That is
necessary, but it does not exercise the parts of this repository that
actually depend on Raspberry Pi hardware and local system integration:

- [rabbitctl.sh](../../rabbitctl.sh) orchestrates the API, bunny UI, and
  voice bridge processes.
- [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
  depends on audio-device, model, and playback behavior that hosted CI
  cannot validate.
- [src/api/skills/open_photoframe.py](../../src/api/skills/open_photoframe.py)
  and [src/api/skills/open_bunny.py](../../src/api/skills/open_bunny.py)
  control external processes and UI transitions.

There is also an important path constraint: several runtime helpers are
still anchored to the current device filesystem layout, including
[rabbitctl.sh](../../rabbitctl.sh) and
[src/api/skills/_paths.py](../../src/api/skills/_paths.py). That means a
hardware workflow cannot be treated like a generic hosted checkout yet;
it has to run on a trusted Pi environment that matches the current path
contract.

The goal of 018B is to add a **separate**, non-blocking, hardware smoke
workflow for that environment.

Out of scope:

- replacing 018A as the primary PR gate
- long-running soak tests or conversation QA
- refactoring all hardcoded runtime paths to make the project fully
  relocatable
- fixing defects discovered by the smoke job; those become follow-up
  tasks

---

## User Decisions (locked)

| Question | Choice |
|---|---|
| Runner type | Dedicated self-hosted Raspberry Pi runner |
| Initial trigger | `workflow_dispatch` only |
| Merge gating | Non-blocking at first |
| Concurrency | Serialize runs so only one job can touch the device at a time |
| Workspace assumption | Runner host must match the repo's current filesystem/path contract |

---

## Pre-flight

- [ ] 017 complete.
- [ ] 018A merged and stable on `main`.
- [ ] A trusted Raspberry Pi self-hosted runner is registered and labeled.
- [ ] The device can already run the repo manually through
      [rabbitctl.sh](../../rabbitctl.sh).
- [ ] `rabbitctl.sh status` is clean before the workflow starts.

---

## Phase A — Define the Hardware Smoke Boundary

### Step 1 — Freeze what the smoke workflow is responsible for

018B should validate only a **minimal** hardware smoke boundary:

- the Pi runner can access the repo in the expected path layout
- config can load successfully
- the managed services can start and stop cleanly
- expected log files are available for triage on failure

It should **not** try to prove:

- full microphone wake-word accuracy
- end-to-end human conversation quality
- performance / latency tuning
- exhaustive photoframe UI correctness

### Step 2 — Name the runner contract explicitly

Document the expected runner labels and host assumptions, for example:

- `self-hosted`
- `linux`
- `arm64`
- a repo-specific label such as `voiceassist-pi`

This avoids accidental scheduling onto the wrong machine.

---

## Phase B — Provision the Workflow Skeleton (depends on A)

### Step 3 — Create `hardware-smoke.yml` under `.github/workflows/`

Add a separate workflow triggered by:

- `workflow_dispatch`

Do not add `pull_request` or `push` triggers in the first iteration.

### Step 4 — Add concurrency protection

Use a workflow or job-level concurrency group so two smoke runs cannot
overlap on the same device.

This is mandatory because the workflow will touch shared local state,
processes, logs, and display/audio resources.

---

## Phase C — Run the Minimal Device Smoke (depends on B)

### Step 5 — Add a narrow smoke script or inline workflow steps

The smoke sequence should stay intentionally small:

1. confirm repo path assumptions
2. confirm config loads
3. start services via [rabbitctl.sh](../../rabbitctl.sh)
4. verify expected processes are up
5. stop services via [rabbitctl.sh](../../rabbitctl.sh)
6. verify cleanup succeeded

If command complexity grows, move it into a dedicated script under a
future `scripts/ci/` path.

### Step 6 — Keep startup checks process-oriented

Use process health and known artifacts rather than interactive audio:

- [rabbitctl.sh](../../rabbitctl.sh) status output
- expected log files under `/tmp/`
- optional ready-file checks where they already exist

Useful existing artifacts include:

- `/tmp/assistant_bridge.log`
- `/tmp/bunny_ui.log`
- `/tmp/voice_bridge.log`
- `/tmp/photoframe.ready`
- `/tmp/voiceassist_signal.json`

### Step 7 — Collect logs on failure

If the smoke run fails, upload the relevant `/tmp/` logs and any narrow
diagnostic output needed to explain whether the failure was in:

- API startup
- bunny UI startup
- voice bridge startup
- photoframe handoff

---

## Phase D — Respect the Current Path Contract (depends on C)

### Step 8 — Do not assume a relocatable checkout

Because current runtime code uses absolute project paths, the hardware
workflow must either:

- run against the canonical repo path on the Pi, or
- explicitly defer execution until those path assumptions are removed in
  a later refactor

For 018B, choose the first option and document it clearly.

### Step 9 — Keep the runner environment stable

Document the expected local state for the dedicated Pi runner:

- required system packages already installed
- audio and display environment available
- no unrelated long-lived processes competing for the same device
- no concurrent developer activity on the same machine during smoke runs

This is necessary to keep the workflow signal interpretable.

---

## Phase E — Keep 018B Non-Blocking Until Proven Stable (depends on D)

### Step 10 — Start as manual, non-blocking validation

Do not make 018B a required PR check initially.

Treat it as:

- a manual release-confidence job, or
- a post-merge / scheduled smoke candidate once it proves reliable

### Step 11 — Reassess only after multiple stable runs

Only consider expanding triggers after the workflow has demonstrated:

- stable runner availability
- repeatable startup / teardown behavior
- low enough flake rate to be actionable

Until then, 018A remains the only merge-gating baseline.

---

## Verification

### Step 12 — Required outcomes before calling 018B done

Expected outcomes:

- manual dispatch completes on the Pi runner without hanging the device
- [rabbitctl.sh](../../rabbitctl.sh) can start and stop the managed
  services inside the workflow
- failures upload enough logs to diagnose the failing layer
- overlapping runs are serialized or rejected cleanly

### Step 13 — Explicit non-goal check

Before closing 018B, verify that the workflow is still non-blocking for
PRs. If it is already wired into required branch protection, that is a
scope error for this phase.
