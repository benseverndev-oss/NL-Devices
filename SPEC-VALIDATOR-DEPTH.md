# Spec — Deepen + Adversarially Test the Validator

> Closes the mechanism half of [`GAPS.md`](./GAPS.md) §4c / §5 item 5: *"only 3
> topological + 2 toy-electrical checks… and the validator was only ever tested on
> faults its authors designed it to catch — no measured false-negative rate."*

The trust layer's whole value is that it *catches real mistakes*. Three hand-picked
faults, all passing, is not evidence of that — it's evidence the authors can write a
test for their own check. This change does two things: **adds real rating/electrical
checks**, and **measures the false-negative rate against known-bad designs the checks
were not built for**.

## 1. Deeper checks (3 → 9)

Added to `seam_validator.py`, registered in `CHECKS`, and fed real data threaded
through `block_contract.build_design`. Each fires only when the design carries the
relevant data, so absent data is a skip — never a false alarm.

| Check key | Rule | Data used |
|---|---|---|
| `current-budget` | Σ(rail loads) ≤ source capacity | sink `current_ma`, source `max_current_ma` |
| `i2c-reserved-addr` | assigned address is valid 7-bit and outside the reserved bands (`0x00–07`, `0x78–7F`) | assigned I2C address |
| `i2c-bus-timing` | bus C ≤ 400pF **and** RC rise time `t_r ≈ 0.8473·R·C` ≤ the per-mode limit (1000/300/120 ns) | pull-up Ω, per-device pin cap, target speed |

Two further checks were later added when their corpus false negatives were closed
(see §2 and "Post-roadmap" below): `part-rail-rating` (ground-truth join),
`power-connectivity` (every active device sits on a rail), and `i2c-multimaster`
(one controller per bus) — taking the gate to **9 checks**.

The original three (`power-domain`, `i2c-pullups`, `i2c-address`) are unchanged. The
authored `sensor_node` slice passes all of them; the three original injected faults still
trip exactly their one check (backward-compatible — verified by `block_contract.py --faults`).

## 2. Adversarial corpus (`validator_corpus.py`) — the measured number

A labelled corpus runs through `validate()` and every design is classified:

- **good** (2) — must pass clean; a failure is a false *positive* → CI fails.
- **bad_covered** (9) — must fire the expected check → regression guard for all nine checks.
- **bad_uncovered** (0 now) — real known-bad designs the gate has **no check for**. They
  slip through *by design*; that is a measured false **negative**. They do **not** fail
  CI — they are the published roadmap. As checks land, entries graduate to `bad_covered`.

```
covered faults:    9   detected 9/9    (was 7 — 'i2c-multimaster' + 'power-connectivity' added)
good designs:      2   (0 false positives)
uncovered faults:  0   still-missed 0
measured false-negative rate (of all 9 known-bad designs): 0/9 = 0%   (was 22%)
```

The `bad_uncovered` set is the honest part — faults chosen *because* no current check
saw them. All three representable FNs have since been **built** and graduated to
`bad_covered`, walking the rate 33% → 22% → 0%:

| Was-missing check | Known-bad design | Status |
|---|---|---|
| ~~`design-level-part-rating`~~ | 5V-only part on a 3.3V rail | ✅ caught (`part-rail-rating`) |
| ~~`i2c-multimaster`~~ | two controllers on one bus | ✅ caught (`i2c-multimaster`) |
| ~~`power-connectivity`~~ | an active device powered by no rail | ✅ caught (`power-connectivity`) |

What remains is the `NOT_MODELLED` list (decoupling adequacy, absolute-max /
reverse-polarity, pin-level ERC on the netlist, thermal, bus-speed-vs-slowest-participant)
— faults today's data model can't even express. **0% is the FN rate over the
*representable* corpus, not a claim of completeness**; a genuinely external corpus of
field-captured bad boards would likely push it back up (see Honest scope).

## Post-roadmap: `part-rail-rating` (joins the validator to the part DB)

The highest-value uncovered FN is now a real check. `seam_validator.check_part_rail_rating`
looks up each sink's **ground-truth datasheet operating range** (from the `verify_parts`
snapshot, attached by `block_contract.build_design(..., snapshot)`) and asserts the rail
voltage the part *actually sees* is within it — catching a part placed on a wrong-voltage
rail even when the hand-typed YAML claims it's fine. The orchestrator gate now loads the
snapshot and runs it, so the real product gate is ground-truth-aware. The corpus's
`bad_part_rail_rating` (a 5V-only part on the 3.3V rail) is now caught.

## CI

`validator_corpus.py` runs in the `spike` job. It **gates on regressions only** (a
good design failing, or a covered fault no longer caught), so the FN inventory is
surfaced on every run without making CI red for known gaps.

## Honest scope

- The corpus is an *internal* adversarial set, not a third-party one. It deliberately
  includes out-of-design faults to make the FN number real, but a genuinely external
  corpus of field-captured bad boards is the stronger next step (and would likely push
  the FN rate up before new checks push it back down).
- ✅ All three representable FNs are now **built**: `part-rail-rating` (see "Post-roadmap"
  above), plus `i2c-multimaster` (two controllers on a bus need arbitration the simple
  composition doesn't provide) and `power-connectivity` (every active device must sit on a
  rail — the orphan-device check). The representable FN rate is now 0/9; the honest frontier
  is the `NOT_MODELLED` list and a field-captured external corpus.
