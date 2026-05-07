# 018A — Add GitHub-Hosted CI and Code Scanning Baseline

## Status: Done ✅ (workflows and docs landed 2026-05-07)

## Motivation

The repository currently has no GitHub Actions workflows under
`.github/workflows/`, so pull requests are not gated by any shared
automation.

At the same time, the current test suite is already good enough to
support a first CI baseline:

- API and routing behavior are covered in
  [tests/test_api.py](../../../tests/test_api.py)
- config and state-file behavior are covered in
  [tests/test_runtime_config.py](../../../tests/test_runtime_config.py)
- local-skill routing behavior is covered in
  [tests/test_voice_bridge_local_routing.py](../../../tests/test_voice_bridge_local_routing.py)
- external OpenAI behavior is already mocked in
  [tests/conftest.py](../../../tests/conftest.py)

The purpose of 018A is to turn that existing coverage into a portable,
GitHub-hosted CI baseline that can:

- gate pull requests
- run Python code scanning
- run dependency scanning
- run a portable secret scan

without requiring Raspberry Pi hardware.

Out of scope:

- self-hosted or Raspberry Pi workflows — moved to 018B.
- rabbitctl live lifecycle checks, photoframe launch, microphone input,
  speaker playback, or other hardware-dependent smoke tests.
- fixing security findings discovered by the new scans — those become
  follow-up work items, likely under 019 or separate plans.

---

## User Decisions (locked)

| Question | Choice |
|---|---|
| Runner type | Use GitHub-hosted runners only |
| Default OS | Start with `ubuntu-latest` |
| Python version | Match current repo target: Python 3.11 |
| PR gating | 018A is the blocking CI baseline once stable on default branch |
| Secret scan tool | Use a repo-portable CI tool; do not assume GitHub Advanced Security is enabled |

---

## Pre-flight

- [ ] 017 complete, or at minimum the dependency manifests are accurate
      enough for a clean install.
- [ ] Snapshot current local baseline:
      `.venv/bin/pytest -q` → expect **76 passed**.
- [ ] Confirm `.github/workflows/` is absent or empty before creating the
  first workflows.
- [ ] `git status -s` clean.

---

## Phase A — Define the Shared CI Contract

### Step 1 — Freeze what 018A will and will not validate

The baseline workflow should validate only checks that are portable on a
hosted Linux runner:

- install dependencies from the normalized manifests
- run pytest
- run CodeQL for Python
- run dependency audit against the Python environment / manifests
- run secret scan against the checked-out repo

Explicitly exclude from 018A:

- `rabbitctl.sh start`
- live UI startup from [src/ui/assistant_ui.py](../../../src/ui/assistant_ui.py)
- hardware audio I/O
- photoframe integration smoke

### Step 2 — Decide the workflow split

Use two workflow files rather than forcing everything into one job:

- `ci.yml` for install + pytest + lightweight scans
- `codeql.yml` for GitHub-native CodeQL analysis

This keeps the PR signal easier to read and rerun.

---

## Phase B — Add the Hosted CI Workflow (depends on A)

### Step 3 — Create `ci.yml` under `.github/workflows/`

Add a workflow triggered on:

- `pull_request`
- `push` to `main`

Core job shape:

- runner: `ubuntu-latest`
- setup Python 3.11
- install from `requirements.txt` and `requirements-dev.txt`
- run pytest with the existing suite

### Step 4 — Keep pytest scope aligned to the current suite

Do not add speculative smoke tests in this plan. The command should stay
close to the current repo contract:

```bash
pytest -q
```

The goal is to reproduce the existing local baseline in CI, not widen
test scope during the same change.

### Step 5 — Add dependency audit to the same workflow

After install, run one Python dependency audit step.

Implementation choice for this plan:

- prefer `pip-audit` because the repo is Python-only and the audit can
  run against the resolved environment created by the workflow

Treat initial findings as reportable results first; do not block merges
until the noise level is understood.

### Step 6 — Add a portable secret scan step

Add one portable secret scan in CI so the repo is covered even if native
platform scanning is not enabled.

This plan only needs the baseline signal; it does not need custom rules
yet.

---

## Phase C — Add CodeQL (parallel with B)

### Step 7 — Create `codeql.yml` under `.github/workflows/`

Use GitHub's standard CodeQL workflow for Python.

Language scope:

- Python only for now

The repo characteristics that justify CodeQL here are already present:

- FastAPI request handling in [src/api/app.py](../../../src/api/app.py)
- subprocess and process-management behavior under
  [src/api/skills/](../../../src/api/skills/)
- file and network I/O in [src/bridge/voice_bridge.py](../../../src/bridge/voice_bridge.py)

### Step 8 — Keep CodeQL independent from hardware assumptions

Do not attempt to run live audio or service startup from CodeQL setup.
The workflow should only build enough context for static analysis.

---

## Phase D — Make Local and CI Checks Consistent (depends on B, C)

### Step 9 — Optionally add a shared verification script

If command duplication between local use and CI becomes noisy, add a
small script under a future `scripts/ci/` path to centralize the core
hosted checks.

This is optional in 018A; the priority is getting the baseline workflow
online, not perfecting local ergonomics.

### Step 10 — Document the CI contract

Update docs so contributors understand:

- which workflows are required for PRs
- which scans are informational vs blocking
- that hosted CI does **not** prove Raspberry Pi hardware behavior

Prefer updating [README.md](../../../README.md) and/or
[AGENTS.md](../../../AGENTS.md) only where this contract is currently
missing.

---

## Phase E — Turn the Baseline into a Merge Gate (depends on D)

### Step 11 — Stabilize on default branch first

Before making checks required in branch protection:

- merge the workflow once
- verify it passes on `main`
- confirm the scan outputs are readable and actionable

### Step 12 — Mark required checks deliberately

After stabilization, require only the checks that are expected to be
reliable:

- main CI / pytest workflow
- CodeQL workflow

Keep dependency audit and secret scan non-blocking until the initial
signal quality is known.

---

## Verification

### Step 13 — Required outcomes before calling 018A done

Expected outcomes:

- A fresh GitHub-hosted run installs successfully from the repo manifests
- pytest completes successfully on the hosted runner
- CodeQL uploads Python analysis results
- dependency audit completes without environment-resolution failure
- secret scan completes and produces triageable results

### Step 14 — PR behavior check

Open a test PR and confirm:

- the workflows trigger automatically
- failure in the hosted CI workflow is visible on the PR
- the repo can adopt those checks as required branch protections after
  stabilization

This PR-level validation is the real success criterion for 018A.
