# Electrical Validation

Replaced the original "Ohm's-law-in-a-SPICE-costume" gate with honest analytics + genuine
simulation, each labelled as what it is.

## Pieces (`spike/`)
- `electrical.py` — one **analytic** check on the gate path: an **LDO dropout margin**
  (`Vin ≥ Vout + Vdropout`), fired where a source block declares `dropout_v` (AMS1117-3.3
  worst-case 1.3 V → a 5→3.3 V rail needs Vin ≥ 4.6 V). Fast, deterministic, no simulator,
  and it has teeth (a 3.6 V input → rejected). Named analytic, not "simulated".
- `spice_sim.py` — **real ngspice `.tran`** runs a calculator can't reproduce: I2C
  open-drain rise time, and rail droop under a load step. `--selftest` cross-checks the
  simulated I2C rise against the analytic `t_r ≈ 0.8473·R·C` limit to **< 5%** and proves
  teeth both ways. Runs live in CI (ngspice is BSD; driven via `ngspice -b`, no GPLv3 PySpice).

## Load-bearing gotcha
The rail-droop deck needs a **series inductance** (frequency-dependent source impedance) —
an ideal source behind a small R makes decoupling irrelevant, which is exactly the trap the
old "theatre" deck fell into.

## Still open
The proven droop sim isn't wired into the *gate* yet (block YAML carries no per-rail
decoupling-cap data); dropout is a worst-case constant, not load/thermal-dependent.

## Source of truth / specs
[`SPEC-SPICE.md`](../../SPEC-SPICE.md), [`GAPS.md`](../../GAPS.md) §3/§5.6.

---
**Classification:** architecture/active • **Last updated:** 2026-06-09
