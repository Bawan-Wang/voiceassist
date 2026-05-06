# 017 — Fix Dependency Manifests and Establish a Clean-Install Baseline

## Status: Done ✅ (clean-install verified 2026-05-06)

## Motivation

The repository currently has a working local dev environment, but the
dependency manifests do not fully describe the code that is actually
executed:

- [src/api/app.py](../../src/api/app.py) directly imports `fastapi` and
  `pydantic`, but [requirements.txt](../../requirements.txt) does not
  currently declare them.
- [src/bridge/voice_bridge.py](../../src/bridge/voice_bridge.py)
  imports `requests` inside the API-routing path, but
  [requirements.txt](../../requirements.txt) does not currently declare
  it.
- [rabbitctl.sh](../../rabbitctl.sh) starts the API via
  `python -m uvicorn`, but `uvicorn` is not currently declared in either
  dependency manifest.
- The project does not currently carry a lockfile or alternate package
  metadata file; the working assumption today is that
  [requirements.txt](../../requirements.txt) and
  [requirements-dev.txt](../../requirements-dev.txt) are the canonical
  installation inputs.

This means the repo can pass in an existing machine-specific `.venv`
while still failing in a clean environment, and any dependency scan or
SBOM built from the current manifests will be incomplete.

This plan fixes the manifests first, then proves that a fresh virtual
environment can install the project and run the existing test suite.

Out of scope:

- GitHub Actions / CodeQL / secret scanning workflows — moved to 018A.
- Raspberry Pi or hardware smoke workflows — moved to 018B.
- Runtime security hardening for the local skill control surface and
  error semantics — moved to 019.
- Model-download integrity verification and secret-loading cleanup —
  moved to 020.

---

## User Decisions (locked)

| Question | Choice |
|---|---|
| Dependency format | Keep the current `requirements.txt` + `requirements-dev.txt` layout for now |
| Direct-vs-transitive policy | Declare packages that are directly imported or directly executed by project entrypoints |
| Verification target | A fresh venv on the current Linux dev environment must install and pass pytest |
| Packaging migration | Do **not** migrate to `pyproject.toml` in this plan |

---

## Pre-flight

- [ ] Snapshot current baseline tests:
      `.venv/bin/pytest -q` → expect **76 passed**.
- [ ] `git status -s` clean.
- [ ] Confirm no existing active dependency-plan has already started in
      `.docs/exec-plans/`.

---

## Phase A — Audit the Current Dependency Surface

### Step 1 — Inventory direct third-party runtime imports

Review direct non-stdlib imports used under [src/](../../src/):

- API / web: `fastapi`, `pydantic`, `openai`
- Bridge / audio / inference: `numpy`, `onnxruntime`, `sounddevice`,
  `webrtcvad`, `requests`, `openai`
- Providers / UI / config: `pygame`, `yaml`, `piper-tts`,
  `sherpa-onnx`

Use the inventory to separate:

- runtime dependencies required by application entrypoints
- dev-only dependencies required by tests and tooling

### Step 2 — Inventory direct execution entrypoints

Confirm packages invoked by entrypoints rather than imported directly:

- [rabbitctl.sh](../../rabbitctl.sh) requires `uvicorn`
- tests require `pytest`, `httpx`, and any library used by
  [fastapi.testclient](../../tests/conftest.py)

### Step 3 — Record the current manifest gap explicitly

Before editing manifests, document the concrete delta between current
imports / entrypoints and the manifests. The expected initial gap is:

- add `fastapi`
- add `pydantic`
- add `requests`
- add `uvicorn`

If the audit finds additional direct dependencies, include them in the
same manifest pass instead of splitting them into follow-up edits.

---

## Phase B — Normalize the Manifests (depends on A)

### Step 4 — Update [requirements.txt](../../requirements.txt)

Adjust the runtime manifest so it explicitly lists every package needed
by the application entrypoints under [src/](../../src/) and
[rabbitctl.sh](../../rabbitctl.sh).

Guidance:

- Preserve the current repo style of simple line-based requirements.
- Keep the existing `>=` floor style unless a specific pin is justified.
- Prefer explicit direct dependencies over relying on transitive
  installation through another package.

### Step 5 — Update [requirements-dev.txt](../../requirements-dev.txt)

Ensure the dev manifest contains the tooling actually used for local
verification and CI, without duplicating the entire runtime file.

At minimum, keep or normalize:

- `pytest`
- `pytest-cov`
- `httpx`

If a dev-only scan tool is introduced later by 018A, add it there in
that plan, not this one.

### Step 6 — Decide whether README install docs need a small correction

Re-check [README.md](../../README.md) after Step 4/5.

Update only if the documented install path no longer matches the actual
manifests or if a fresh install requires a newly documented command.

---

## Phase C — Prove a Clean Install (depends on B)

### Step 7 — Create a throwaway verification venv

Do **not** reuse the repository `.venv/` for this proof.

Use a disposable environment outside the repo, for example:

```bash
python3 -m venv /tmp/voiceassist-clean-venv
/tmp/voiceassist-clean-venv/bin/pip install -U pip
/tmp/voiceassist-clean-venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

The goal is to prove the manifests are self-sufficient.

### Step 8 — Run the test suite from the clean environment

```bash
/tmp/voiceassist-clean-venv/bin/pytest -q
```

Expected result: **76 passed**.

If the clean environment fails because a dependency is missing, fix the
manifest gap directly and rerun the same command before widening scope.

### Step 9 — Sanity-check the declared entrypoints

Run narrow import / command smoke checks from the clean venv:

```bash
/tmp/voiceassist-clean-venv/bin/python -c "from src.api.app import app; print('api ok')"
/tmp/voiceassist-clean-venv/bin/python -c "import uvicorn, requests; print('entrypoint deps ok')"
```

This confirms the packages required by the runtime entrypoints are truly
present after a clean install.

---

## Phase D — Wrap-up (depends on C)

### Step 10 — Summarize the normalized dependency policy

Add or adjust a short note in the docs clarifying:

- `requirements.txt` is the runtime source of truth
- `requirements-dev.txt` layers tooling on top of runtime
- CI and scans depend on these manifests being accurate

Prefer updating [README.md](../../README.md) or [AGENTS.md](../../AGENTS.md)
only if that guidance is missing or misleading.

### Step 11 — Leave lockfile / packaging migration for a later plan

Do **not** expand 017 into a packaging-system migration. If a lockfile,
`pyproject.toml`, or pip-tools workflow is desired later, spin a separate
plan after 018A is stable.

---

## Verification

### Step 12 — Required checks before calling 017 done

```bash
.venv/bin/pytest -q
python3 -m venv /tmp/voiceassist-clean-venv
/tmp/voiceassist-clean-venv/bin/pip install -U pip
/tmp/voiceassist-clean-venv/bin/pip install -r requirements.txt -r requirements-dev.txt
/tmp/voiceassist-clean-venv/bin/pytest -q
/tmp/voiceassist-clean-venv/bin/python -c "from src.api.app import app; print('api ok')"
/tmp/voiceassist-clean-venv/bin/python -c "import uvicorn, requests; print('entrypoint deps ok')"
```

Expected:

- repo `.venv` still passes **76 tests**
- clean-install venv also passes **76 tests**
- no missing-module failures for direct runtime imports or entrypoints

### Step 13 — Optional grep sweep

Use a final search to confirm that any newly declared package is backed
by a real direct import or runtime entrypoint.

This is a sanity check only; it does not replace the clean-install proof.
