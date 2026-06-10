# Roadmap

The Phase-0 spike de-risked the validator and the compile-to-manufacturable-BOM path, and
(PR #8) closed the routing → copper → fab pillar for one vertical. What's left, by leverage
(none blocking; honest distance tracked in [`GAPS.md`](../../GAPS.md)):

## Highest leverage
- **Prove the NL leg for real.** The eval runs a `FakeModel`; run `--live` and record it.
  Until then the product's namesake is unproven, not "done"
  ([../architecture/nl-orchestrator.md](../architecture/nl-orchestrator.md)).
- **Wire the STM32 block into a build target** for a fuller routed board (MCU + LDO +
  EEPROM). It exists in the parts lib but no `App` uses it — an atopile design change, the
  natural next routing step ([../decisions/0004-route-the-verified-board.md](../decisions/0004-route-the-verified-board.md)).

## Validator / electrical depth
- Two remaining false-negative checks: `power-connectivity` (cheap) and `i2c-multimaster`.
- Wire the proven decoupling-droop sim into the gate (needs per-rail cap data in block YAML).
- Pin-level ERC on the composed netlist (SKiDL ERC never wired into the gate).

## Routing / fab fidelity
- DFM-aware placement (thermal, edge keep-out) instead of the deterministic grid.
- Pin the LCSC part-pick to the snapshot for a fully offline `ato build`.

## Data + breadth
- Datasheet → structured-data extraction pipeline (named BUILD IP, currently 0 — `GAPS` §4b).
- Block-library breadth: a 2nd power topology + a non-I2C bus, to stress the validator.

## Business (not codeable — Ben's)
- The cheapest test: 5–10 customer-discovery calls on respin willingness-to-pay + one fab
  partner conversation on wholesale margin — the two assumptions the revenue model rests on
  ([`BUSINESS.md`](../../BUSINESS.md), `GAPS` §8).

---
**Classification:** planning/active • **Last updated:** 2026-06-09
