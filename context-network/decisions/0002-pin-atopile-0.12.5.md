# 0002 — Pin atopile 0.12.5 / Python 3.13

**Status:** accepted + shipped (DECISION step 1) • **Human sign-off:** Ben

## Context
atopile is the compile-to-netlist substrate. Newer atopile (0.13+) requires Python 3.14,
which is an RC that crashes in this environment. Unpinned tooling drifts and breaks CI
non-reproducibly.

## Decision
Pin **atopile 0.12.5 on Python 3.13**, declared in one place and linted for consistency:
`.python-version`, `ato.yaml` floor, both `scripts/setup.sh`/`.ps1`, cross-checked by
`scripts/check_toolchain.py` (offline, in the `spike` CI job). The live install is proven
separately by the `toolchain` CI job. The 3.13 pin caps atopile to 0.12.x by construction.

## Consequences
- Any atopile bug present in 0.12.5 must be worked around, not bumped past (e.g. the
  part-pick `.step` model issue — [0005](0005-commit-3d-models.md)).
- `check_toolchain.py` was later extended to also pin KiCad 9 + freerouting 2.1.0
  ([0003](0003-own-the-autoroute.md)).

## Source
[`DECISION.md`](../../DECISION.md), [`GAPS.md`](../../GAPS.md) §4g.

---
**Classification:** decision/accepted • **Last updated:** 2026-06-09
