# 0005 — Commit the per-part 3D models (~25 MB) for reproducible builds

**Status:** accepted + shipped (2026-06-09, PR #8) • **Human sign-off:** Ben, 2026-06-09

## Context
`ato build` failed deterministically in CI with `FileNotFoundError` on each part's `.step`
3D model. Root cause: every auto-generated part `.ato` declares `model="…step"`, but
`spike/.gitignore` had blanket-ignored `*.step`, so the models existed nowhere in the repo
and atopile 0.12.5's part-pick `attach` requires them. (The pin caps us at 0.12.x, so we
can't bump past the bug — [0002](0002-pin-atopile-0.12.5.md).)

## Decision
Fetch the real models and **commit them** (un-ignore `*.step`), so builds are reproducible
with complete part data. Fetch mechanism: `ato create part -s <LCSC> -a` (non-interactive)
into a scratch project, then copy each `.step` into its committed part dir under the exact
name the `.ato` expects. 11 models, ~25 MB. Ben chose "complete part data" over the leaner
alternatives (strip the model attr / placeholder stubs / re-fetch every CI run).

## Consequences
- `spike/atopile/elec/src/parts/**/*.step` are tracked; the `route` job's `ato build` is
  reproducible with no per-run model fetch (only the LCSC part-pick still hits the network).
- ~25 MB of binary STEP in a showcase repo — accepted for fidelity.
- Mechanism note: the dev sandbox can't pull CI artifacts (Azure blob unreachable), so the
  models were committed *by CI* (`[skip ci]` + `contents: write`), then pulled — see
  [processes/development-workflow.md](../processes/development-workflow.md).

## Source
[../architecture/autoroute-pipeline.md](../architecture/autoroute-pipeline.md).

---
**Classification:** decision/accepted • **Last updated:** 2026-06-09
