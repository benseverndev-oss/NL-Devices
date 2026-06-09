# Spec — Replace the SPICE Theatre with Real Sims (or Honest Analytics)

> Closes [`GAPS.md`](./GAPS.md) §3 row 3 / §5 item 6: *"ngspice is invoked, but the
> decks are an ideal source behind a 0.1Ω resistor and a resistor divider — Ohm's-law
> arithmetic dressed as SPICE. The only failure paths are explicit comparisons that
> need no simulator."*

The fix does **both** things the gap offered, and labels which is which.

## The theatre that was removed

`electrical.py` used to build two ngspice decks:
- `Vreg VREG 0 3.3 / Rout VREG RAIL 0.1 / Rload RAIL 0 …` — an ideal source behind
  0.1Ω. It cannot sag out of tolerance; the real pass/fail was the `load_ma > max_ma`
  line beside it.
- `V3 / Rp / Rdev` — a resistor divider; the "sink current" was `(V−Vscl)/Rp`, i.e.
  Ohm's law. ngspice computed a number a calculator gives directly.

Both are gone.

## 1. Honest analytics on the gate path (`electrical.py`)

`check_electrical(slice_doc, lib)` (still called by the orchestrator gate) now runs
exactly one check and **names it analytic**: an **LDO dropout margin** — a linear
regulator needs `Vin ≥ Vout + Vdropout` or it falls out of regulation. It fires only
where the source block declares `dropout_v` (added to `power_3v3_ldo.yaml`: AMS1117-3.3
worst-case **1.3V**, so the 5V→3.3V rail needs Vin ≥ 4.6V). Fast, deterministic, no
simulator — and it has teeth (a 3.6V input → 0.3V margin → rejected).

Current-budget and the analytic I2C rise-time limit live in `seam_validator`
(GAPS #5); this module no longer pretends any of them are simulated.

## 2. Genuine ngspice transient sims (`spice_sim.py`)

Real `.tran` runs whose results a calculator can't produce directly:

| Sim | Deck | Measures |
|---|---|---|
| `sim_i2c_rise_ns(R, C)` | open-drain line released at t=0, pulled up through R into C (`.ic`+`uic`) | ngspice `.meas` 30%→70% rise time |
| `sim_rail_droop_v(Vnom, Rout, C, Istep)` | rail = Vnom behind a series **inductance** + Rout, with C decoupling, hit by a load-current `PULSE` | `.meas` minimum rail voltage (droop) |

The rail-droop sim's inductance is load-bearing: a real power-distribution network has
*frequency-dependent* source impedance (low at DC, high for a fast transient), so the
regulator can't slew quickly and the decoupling cap must supply the charge. Without it,
an ideal source behind a small resistor holds the rail up regardless of C — which is
exactly the trap the old theatre fell into.

ngspice is BSD-licensed; we drive the binary directly (`ngspice -b`), no GPLv3 PySpice.

### Why this isn't theatre too: it's cross-checked
`spice_sim.py --selftest` (run in CI, where ngspice is installed) asserts:
- the simulated I2C rise time agrees with the analytic `t_r ≈ 0.8473·R·C` used by
  `seam_validator.check_i2c_bus_capacitance` to **< 5%** — so the cheap always-on
  analytic limit is *validated by a real simulation*;
- a weak 47kΩ pull-up's measured rise **> 300ns** (caught at fast-mode);
- an under-decoupled rail (100nF) droops **below** 3.135V under a 200mA step while an
  adequately-decoupled one (100µF) holds — the sim has teeth in both directions.

Offline (no ngspice, e.g. a Windows dev box) the self-test still verifies the `.meas`
parser against a captured sample and the analytic reference, and clearly reports that
the live sims run in CI.

## CI

The `spike` job (which already installs ngspice) runs `python3 electrical.py` and
`python3 spice_sim.py --selftest` — so the **real** transient sims execute on every CI
run, not just the analytics.

## Honest scope / what's next

- The droop sim proves the **decoupling-adequacy** capability (a measured false
  negative from GAPS #5), but the *gate* doesn't wire it yet — block YAML carries no
  per-rail decoupling capacitance. Adding that datum turns the proven sim into a gate
  check.
- Still analytic-only at the gate: dropout is a worst-case constant, not load- and
  temperature-dependent. A behavioural LDO model (load/line regulation, thermal) is
  the higher-fidelity next step if a check needs it.
