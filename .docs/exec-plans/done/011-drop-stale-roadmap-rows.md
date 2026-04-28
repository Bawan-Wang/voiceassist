````markdown
# 011 — Drop Stale Roadmap Rows from `PLAN.md`

## Status: Planned 🟡

## Motivation

`PLAN.md`'s "Overall Progress" table currently lists two future phases that
are **not** part of the actual project roadmap:

| Phase | Description                | Status     |
|-------|----------------------------|------------|
| 10    | VLM model bridge           | 🔲 Planned |
| 11    | Taiwan server racing fix   | 🔲 Planned |

These rows were carried over from the early scaffolding period (see
`.docs/exec-plans/done/002-vlm-model-bridge.md` and
`003-taiwan-server-racing-fix.md`, both already archived as Done) and no
longer reflect work the owner intends to do. Leaving them in `PLAN.md`
implies a backlog that does not exist and confuses future contributors
(and any AI agent reading the plan).

This plan removes those two rows. Pure documentation change.

---

## Pre-flight

- [ ] Confirm there is no in-flight branch editing `PLAN.md` (avoid
      conflicts).
- [ ] Confirm no other doc references those phase numbers as upcoming work
      (`grep -rni 'VLM model bridge\|Taiwan server racing' .docs/ PLAN.md`).
      Hits inside `.docs/exec-plans/done/` are historical and stay.

---

## Action Items

### Step 1 — Edit `PLAN.md` progress table

- [ ] Open `PLAN.md` and locate the "Overall Progress" table.
- [ ] Delete the two trailing rows:
  ```
  | 10 | VLM model bridge | 🔲 Planned |
  | 11 | Taiwan server racing fix | 🔲 Planned |
  ```
- [ ] Do **not** renumber any other phase. Phases 1–9 keep their numbers
      so historical commit messages and exec-plan cross-references
      (e.g. "Phase 7 = exec-plan 007") stay valid.

### Step 2 — Coordinate with 009

- [ ] If 009 has not yet landed: 009 will add a new
      `| 12 | Drop OpenClaw fallback route (exec-plan 010) | 🔲 Planned |`
      row. After 011 lands, 009 should add that as `| 10 |` instead
      (next free number after the deletion).
- [ ] If 009 has already landed before 011: when removing rows 10/11 in
      this plan, also renumber the OpenClaw row down to `| 10 |` so the
      table stays contiguous. Update `009-docs-drop-openclaw-route.md`
      Step 1 to match.

### Step 3 — Sweep for dangling references

- [ ] `grep -n 'Phase 10\|Phase 11\|phase 10\|phase 11' .docs/ PLAN.md -r`
      — should return nothing (or only matches inside
      `.docs/exec-plans/done/`).
- [ ] If any active doc cites "Phase 10" / "Phase 11" as upcoming work,
      rewrite those sentences in the same commit.

---

## Acceptance Criteria

- [ ] `PLAN.md` "Overall Progress" table no longer contains "VLM model
      bridge" or "Taiwan server racing fix" rows.
- [ ] Phases 1–9 keep their original numbering.
- [ ] No active doc (outside `.docs/exec-plans/done/`) references the
      removed phases as planned work.
- [ ] No code change. `pytest` not required; if run anyway, results match
      `main` exactly.
- [ ] Commit: `docs(011): drop stale VLM/Taiwan-racing rows from PLAN.md`

---

## Rollback Plan

Pure docs change. To restore, `git revert <commit-of-011>`.

---

## Out of Scope

- Editing `.docs/exec-plans/done/002-vlm-model-bridge.md` or
  `003-taiwan-server-racing-fix.md` — those are historical records of
  completed work and stay as-is.
- Any change to runtime code, tests, or other docs unrelated to the
  removed rows.
- Re-evaluating whether voiceassist *should* eventually grow a VLM bridge
  or a Taiwan-server fix — that is a product decision, not in this plan.

---

## Dependencies & Risks

- **No code dependency.** This is documentation hygiene.
- **Risk**: future readers wondering "where did Phase 10/11 go?" — mitigated
  by leaving this plan (011) and the archived 002 / 003 plans in place as
  the audit trail.

````
