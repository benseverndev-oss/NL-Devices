# Seam Validator (the gate)

The deterministic engine that owns correctness — the moat brick. A planner is never
trusted; whatever it composes must pass this gate before anything is built.

## What it checks (`spike/seam_validator.py`) — 7 checks
power-domain · i2c-pullups · i2c-address · current-budget · i2c-reserved-addr ·
i2c-bus-timing (RC rise time vs bus capacitance) · **part-rail-rating** (the rail voltage
a part *actually sees* vs its ground-truth datasheet operating range — joins the validator
to the part DB via `block_contract.build_design(slice, blocks, snapshot)`).

## How it's fed
`spike/block_contract.py` loads block YAML and composes a validatable `Design`
(rails/buses/nodes). With a part snapshot attached, `part-rail-rating` becomes
ground-truth-aware. The orchestrator gate calls `validate(design)` + the analytic
electrical check.

## Why it's trusted: the FN rate is *measured*
`spike/validator_corpus.py` runs a labelled adversarial corpus (good / bad-covered /
bad-uncovered) and reports a real number: **7/7 covered faults caught, 0 false positives,
2/9 = 22% false-negative rate.** CI gates on covered-fault regressions only; the remaining
FNs (`power-connectivity`, `i2c-multimaster`) are *published, not hidden*. Whole-design
pin-level ERC is still not wired in (a named gap).

## Source of truth / specs
[`SPEC-VALIDATOR-DEPTH.md`](../../SPEC-VALIDATOR-DEPTH.md), [`GAPS.md`](../../GAPS.md) §4c.
Joined to the part DB: [ground-truth-partdb.md](ground-truth-partdb.md). Founding rationale:
[decisions/0001](../decisions/0001-validation-is-the-product.md).

---
**Classification:** architecture/active • **Last updated:** 2026-06-09
