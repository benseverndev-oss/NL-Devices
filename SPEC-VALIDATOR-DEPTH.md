# Spec — Deepen + Adversarially Test the Validator

> Closes the mechanism half of [`GAPS.md`](./GAPS.md) §4c / §5 item 5: *"only 3
> topological + 2 toy-electrical checks… and the validator was only ever tested on
> faults its authors designed it to catch — no measured false-negative rate."*

The trust layer's whole value is that it *catches real mistakes*. Three hand-picked
faults, all passing, is not evidence of that — it's evidence the authors can write a
test for their own check. This change does two things: **adds real rating/electrical
checks**, and **measures the false-negative rate against known-bad designs the checks
were not built for**.

## 1. Deeper checks (3 → 6)

Added to `seam_validator.py`, registered in `CHECKS`, and fed real data threaded
through `block_contract.build_design`. Each fires only when the design carries the
relevant data, so absent data is a skip — never a false alarm.

| Check key | Rule | Data used |
|---|---|---|
| `current-budget` | Σ(rail loads) ≤ source capacity | sink `current_ma`, source `max_current_ma` |
| `i2c-reserved-addr` | assigned address is valid 7-bit and outside the reserved bands (`0x00–07`, `0x78–7F`) | assigned I2C address |
| `i2c-bus-timing` | bus C ≤ 400pF **and** RC rise time `t_r ≈ 0.8473·R·C` ≤ the per-mode limit (1000/300/120 ns) | pull-up Ω, per-device pin cap, target speed |

The original three (`power-domain`, `i2c-pullups`, `i2c-address`) are unchanged. The
authored `sensor_node` slice passes all six; the three original injected faults still
trip exactly their one check (backward-compatible — verified by `block_contract.py --faults`).

## 2. Adversarial corpus (`validator_corpus.py`) — the measured number

A labelled corpus runs through `validate()` and every design is classified:

- **good** (2) — must pass clean; a failure is a false *positive* → CI fails.
- **bad_covered** (6) — must fire the expected check → regression guard for all six checks.
- **bad_uncovered** (3) — real known-bad designs the gate has **no check for**. They
  slip through *by design*; that is a measured false **negative**. They do **not** fail
  CI — they are the published roadmap.

```
covered faults:    6   detected 6/6
good designs:      2   (0 false positives)
uncovered faults:  3   still-missed 3
measured false-negative rate (of all 9 known-bad designs): 3/9 = 33%
```

The `bad_uncovered` set is the honest part — faults chosen *because* no current check
sees them:

| Missing check | Known-bad design that slips through |
|---|---|
| `i2c-multimaster` | two controllers on one bus |
| `power-connectivity` | an active device powered by no rail |
| `design-level-part-rating` | a part whose YAML rating fits the rail but is wrong in reality (the part is checked in isolation by `verify_parts`, never against the rail it actually sees) |

Plus a `NOT_MODELLED` list (decoupling adequacy, absolute-max / reverse-polarity,
pin-level ERC on the netlist, thermal, bus-speed-vs-slowest-participant) that today's
data model can't even express — the longer roadmap.

## CI

`validator_corpus.py` runs in the `spike` job. It **gates on regressions only** (a
good design failing, or a covered fault no longer caught), so the FN inventory is
surfaced on every run without making CI red for known gaps.

## Honest scope

- The corpus is an *internal* adversarial set, not a third-party one. It deliberately
  includes out-of-design faults to make the FN number real, but a genuinely external
  corpus of field-captured bad boards is the stronger next step (and would likely push
  the FN rate up before new checks push it back down).
- `design-level-part-rating` is the highest-value next check: it joins this validator
  to the `verify_parts` ground-truth layer — checking the voltage each part *actually
  sees on its rail* against the part's datasheet rating, not just the block's YAML.
