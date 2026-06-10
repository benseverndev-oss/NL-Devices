# Design: real STM32 on the `verified` board + two validator false-negative checks

**Date:** 2026-06-09
**Status:** Approved (design); implementation pending
**Trunk:** `claude/brainstorm-idea-vegk59` (tip `98424ef`)

## Summary

Two independent, CI-gated workstreams that harden the existing pipeline, sequenced
board-first:

1. **Real STM32 on the `verified` board.** The board CI routes today
   (`verified_slice.ato:App`) composes a *stub* `McuBlock` — a decoupling cap and I2C
   pull-ups, **no actual chip**. Swap it for the real `McuBlock` (STM32F103C8T6) that
   already exists in `verified_lib.ato`, so the routed board actually computes. Proves
   the autoroute scales from passives + EEPROM to a 48-pin LQFP MCU at the hard
   0-unrouted / 0-DRC gate.
2. **Two validator false-negative checks.** Add `power-connectivity` and
   `i2c-multimaster` to `seam_validator.py`. The adversarial corpus already stages both
   faults as published false-negatives; implementing the checks and reclassifying those
   corpus entries drops the measured false-negative rate from 2/9 (22%) to 0/9 (0%) and turns
   them into hard regression guards.

The two workstreams touch disjoint code and disjoint CI gates and can land
independently. If STM32 routing needs board-param iteration, the validator work still
lands on its own.

## Goals

- The `verified` build target produces and **routes** a board containing a real
  STM32F103C8T6 (MCU) + AMS1117-3.3 (LDO) + AT24C256 (EEPROM), at **0 unrouted nets,
  0 DRC violations**, on **2 copper layers**, with a complete fab package.
- The routed `verified` board and the orchestrator's codegen board share **one**
  block library (no divergent stub vs. real definitions).
- `seam_validator` gains `power-connectivity` and `i2c-multimaster`; the adversarial
  corpus reports a **0% measured false-negative rate** over its representable known-bad
  designs, with both new checks enforced as regression guards in CI.

## Non-goals (YAGNI)

- DFM-aware placement (decoupling caps near their owner, thermal/edge keep-out). The
  deterministic grid in `place.py` stays; the gate is DRC + connectivity, not signal
  integrity.
- 4-layer copper, unless 2-layer routing is empirically proven not to converge.
- Regenerating the offline `place.py` / `route.py` test fixture to match the new board
  (the fixtures test the pure parsers; any valid board exercises them).
- Inventing new `bad_uncovered` corpus entries to keep that list non-empty. The
  remaining roadmap stays in `NOT_MODELLED`.

---

## Workstream 1 — real STM32 on the `verified` board

### Current state

- `spike/atopile/ato.yaml` build target `verified` → `verified_slice.ato:App`.
- `spike/atopile/verified_slice.ato` defines its **own** `PowerBlock`, `McuBlock`,
  `SensorBlock`. Its `McuBlock` is a stub: a 100nF cap + SCL/SDA pull-ups, **no MCU
  part instantiated**.
- `spike/atopile/verified_lib.ato` is the shared block library `codegen.py` emits the
  orchestrator's App from. Its `McuBlock` instantiates the real
  `STMicroelectronics_STM32F103C8T6_package` with full power (every VDD/VSS), decoupling
  (3×100nF + 4.7µF bulk + 1µF on VDDA), reset RC (10k + 100nF on NRST), BOOT0 pulldown,
  and I2C1 on PB6/PB7 with bus pull-ups. Its EEPROM block is named `EepromBlock`.
- The STM32 part is **already fully committed** under
  `spike/atopile/elec/src/parts/STMicroelectronics_STM32F103C8T6/`: `.ato`, `.kicad_sym`,
  `.kicad_mod`, and the `LQFP-48 …​.step` 3D model (alongside the other committed part models).

### The change (Approach A — import from the shared lib)

- **`spike/atopile/verified_slice.ato`:** remove the three local stub block
  definitions; add `from "verified_lib.ato" import PowerBlock, McuBlock, EepromBlock`;
  keep `App` composing `psu` (PowerBlock), `mcu` (McuBlock), `sensor` (EepromBlock) on
  the 3V3 rail with the 400kHz I2C bus. Two `App` changes: (a) the sensor block type
  rename `SensorBlock` → `EepromBlock`; (b) **strap the EEPROM address pins** — the
  imported `EepromBlock` straps `WP` internally but (unlike the old stub `SensorBlock`)
  leaves `A0`/`A1`/`A2` to the parent, so `App` must tie `sensor.eeprom.A0/A1/A2 ~
  power3v3.lv` to hold address 0x50. Left unstrapped they float: harmless to the 0/0 DRC
  gate, but wrong for a board meant to be real (the EEPROM wouldn't reliably answer at
  0x50), and it would undercut the I2C address reasoning the validator assumes.
- **No other files change.** The part + footprint + `.step` are committed; `place()`
  auto-grows the board outline for the additional footprints; the `route` job already
  targets `verified`.

### Fallback (Approach A′ — inline)

If atopile 0.12.5 cross-file `import` or the `parts/…` relative-path resolution fails
when `verified_slice` imports from `verified_lib` (surfaces as an `ato build -b verified`
error on the first CI run), inline the real `McuBlock` body (and the STM32 part import)
directly into `verified_slice.ato`, replacing the stub, and remove the now-redundant
block defs from `verified_lib.ato` so there is still a single source of truth. Same
board; the dedup target (one block definition, not two) is preserved.

### Routing-convergence policy

- The `route` job gate stays **hard**: `spike/route.py --pipeline` exits nonzero unless
  **0 unrouted nets** (`"incomplete_count": 0` from freerouting) **and 0 DRC
  violations**, with all of `route.py`'s `REQUIRED_LAYERS` (`F.Cu`, `B.Cu`, `Edge.Cuts`,
  `drill`) present in the Gerber/drill output.
- Target **2 layers** (an STM32F103 + LDO + EEPROM is a classic 2-layer board). The
  grid placement spreads parts with a 2mm courtyard gap + 5mm edge margin, leaving wide
  routing channels.
- **Escalation ladder**, applied only if the first CI route misses 0/0, smallest change
  first:
  1. Increase freerouting effort (raise `-mp` passes above the current 100).
  2. Widen `place.SPACING_MM` to open more routing channels.
  3. **Last resort:** 4-layer copper — changes `route.py:REQUIRED_LAYERS`, the
     `export_gerbers` layer set (add `In1.Cu`/`In2.Cu`), and the KiCad stackup. Only if
     2-layer is empirically proven not to converge.

### Success criteria (Workstream 1)

- `ato build -b verified` produces a `.kicad_pcb` whose footprints include the
  STM32F103C8T6 (LQFP-48), AMS1117-3.3, and AT24C256.
- The `route` job passes: 0 unrouted, 0 DRC, real `F.Cu` + `B.Cu` copper, all
  `REQUIRED_LAYERS` present.
- `fab_export` routed-package build + validation passes for the new board.
- `verified_slice.ato` and `verified_lib.ato` share one definition of each block.

---

## Workstream 2 — validator false-negative checks

### Current state

- `spike/seam_validator.py` registers 7 checks in `CHECKS`, each
  `(Design) -> list[str]`. The model: `Design` has `rails: list[PowerRail]` and
  `buses: list[I2CBus]`; `I2CNode` has `role ∈ {'controller','peripheral'}`; a rail's
  `sinks` are `(block, req_v, tol)` tuples.
- `spike/validator_corpus.py` runs a labelled corpus through `validate()` and reports a
  measured false-negative rate. It already contains two `bad_uncovered` entries (do not
  fail CI; published as the honest FN inventory):
  - `_uncov_multimaster` — appends a second `controller` (`mcu2`) to the bus; `missing:
    "i2c-multimaster"`.
  - `_uncov_floating_power` — appends a peripheral (`orphan`, 0x51) that no rail powers;
    `missing: "power-connectivity"`.
- CI runs `python3 validator_corpus.py` in the `spike` job; it gates on covered-fault
  regressions and on good-design false positives.

### The change

**`spike/seam_validator.py`** — add two checks and register them in `CHECKS`:

- `check_power_connectivity(d)`: build `powered = {block for r in d.rails for (block,
  *_ ) in r.sinks}`. For every `I2CNode` on every bus, if `n.block not in powered`,
  emit `POWER: block '<n.block>' on bus '<bus>' draws from no rail (power floats)`.
- `check_i2c_multimaster(d)`: for each bus, collect `controllers = [n.block for n in
  b.nodes if n.role == 'controller']`; if `len(controllers) > 1`, emit `I2C: bus
  '<bus>' has <N> controllers (<names>); multi-master not supported`.

Register as `("power-connectivity", check_power_connectivity)` and
`("i2c-multimaster", check_i2c_multimaster)` in `CHECKS`.

**`spike/validator_corpus.py`** — reclassify and clean the two fixtures so each fires
*exactly* its intended check:

- `_uncov_multimaster` → `kind: "bad_covered", expect: {"i2c-multimaster"}`. Add `mcu2`
  to the 3V3 rail `sinks` so it does not also trip `power-connectivity`.
- `_uncov_floating_power` → `kind: "bad_covered", expect: {"power-connectivity"}`. The
  `orphan` node stays off every rail — that *is* the fault.
- `_bad_addr_collision`: add `sensor_b` to the 3V3 rail `sinks`, so the address-collision
  case fires only `i2c-address` (today `sensor_b` floats; the new connectivity check
  would otherwise co-fire — harmless under the corpus's subset logic, but cleaner as a
  single-fault fixture).

### Interaction check (no false positives introduced)

- `good_baseline` / `_good_fast_bus`: bus nodes `mcu`, `sensor` are both 3V3 sinks →
  power-connectivity clean; one controller → multimaster clean.
- `_bad_part_rail_rating`: adds `hv_only_sensor` to both the rail and the bus → powered,
  no co-fire.
- All other `bad_covered` fixtures keep their single expected check (subset logic
  tolerates extra failures regardless, but the fixture fixes above keep them clean).
- `seam_validator.py`'s own `__main__` selftest computes its verdict from only the
  `power-domain` / `i2c-pullups` / `i2c-address` columns, so adding checks to `CHECKS`
  does not affect it.
- **Wider blast radius (beyond the corpus): `CHECKS` runs everywhere `sv.validate()` is
  called.** `block_contract.py --faults` injects an address-collision fixture
  (`inject_faults` fault 3) that appends `sensor_b` to the bus without a rail, and
  asserts the *exact* failing-check set — so `power-connectivity` co-fires and breaks it.
  Same one-line fix as the corpus: power `sensor_b` on the 3V3 rail. The
  orchestrator/eval composer (`orchestrator._compose`) derives `rail3_sinks` and
  `bus_members` from the same instance lists, so every bus node is always a rail sink and
  there is one controller — those composed designs are clean by construction (no fix
  needed); `eval_planner` reject-cases use substring matching, tolerant of extra checks.

### Success criteria (Workstream 2)

- `python3 validator_corpus.py` exits 0: 0 false positives, 0 covered-fault regressions,
  both new checks catch their (now `bad_covered`) cases, and the reported **measured
  false-negative rate is 0/9 (0%)** over the known-bad designs (the harness denominator
  is `total_bad = bad_covered + bad_uncovered`; the 2 `good` designs are not counted).
- `python3 seam_validator.py` still exits 0.
- `NOT_MODELLED` unchanged (the genuinely-unrepresentable roadmap remains published).

---

## Testing & CI

- **`spike` job** (offline, existing): `validator_corpus.py` enforces both new checks;
  `seam_validator.py` selftest unaffected. No new dependencies.
- **`route` job** (existing): builds and routes the real STM32 `verified` board at the
  hard 0/0 gate; `fab_export` validates the routed package.
- No workflow structure changes are required; both gates already run on push/PR.

## Risks

- **LQFP-48 fanout convergence.** A 0.5mm-pitch 48-pin part is the routing stress case.
  Mitigated by the escalation ladder; the 2-layer assumption is validated empirically on
  the first CI run, not asserted.
- **atopile cross-file import / part-path resolution** for Approach A. Mitigated by the
  inline fallback (A′), which produces the identical board.
- **CI minutes.** The `route` job runs a full freerouting pass on a larger board (more
  nets → longer route). Acceptable; still one routed board (Approach C's second target
  was rejected to avoid doubling route time).

## Rollout

Board first (it exercises the route gate and is the higher-risk change), then the
validator checks. Each is a separate commit / PR off trunk, merged on green, per the
repo cadence.
