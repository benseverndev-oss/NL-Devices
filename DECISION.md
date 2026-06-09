# Spike Decision Memo — Substrate & Architecture

> Capstone of the Phase-0 spike ([`SPIKE.md`](./SPIKE.md), results in
> [`spike/README.md`](./spike/README.md)). Steps 0–5 ran end-to-end; this is Step 6
> — the filled scorecard and the decision.

## TL;DR

**Adopt a hybrid, with atopile as the authoring substrate.**

> **atopile** (typed seams + constraint solver + manufacturable passives) for
> authoring · **our own seam-validator** (substrate-independent, ~150 lines) for the
> I2C/topology rules atopile doesn't enforce · **ngspice** (BSD) for electrical
> sanity · **SKiDL/KiCad** kept as the reference for IC component definitions +
> pin-level ERC.

The spike **de-risked Risk #1** (is the verified-block + seam-validation thesis
real?): **yes** — the seam-validation moat is real, small, and deterministic, and
atopile pre-builds the hardest check for free. The real cost is the **verified-block
/ IC part-data library**, not the validator.

## Filled scorecard (observed in steps 1–5; 1–5 scale)

| Dimension | Wt | atopile | SKiDL | Evidence |
|---|:--:|:--:|:--:|---|
| **Typed port contract** (voltage domain, I2C) | ×3 | **5** | 2 | atopile native `ElectricPower`/`I2C`; SKiDL bare nets |
| **Seam-check leverage** (free validation) | ×3 | **4** | 2 | atopile caught Fault 1 (power domain) via solver; both miss I2C topology |
| **Programmatic drivability** (LLM target) | ×3 | **4** | 4 | `.ato` text w/ typed guardrails vs. pure Python; both generable |
| **Electrical / SPICE** | ×2 | 1 | **5** | SKiDL→ngspice; atopile none (we use ngspice harness regardless) |
| **Part resolution + manufacturability** | ×2 | **4** | 3 | atopile auto-picks passives→**LCSC MPNs**; SKiDL names ICs but no MPN |
| **Extensibility for custom validator** | ×2 | 4 | 4 | validator is substrate-independent (runs on our block-graph) |
| **Maturity / bus-factor** | ×1 | 3 | 3 | atopile: active but py3.14 churn; SKiDL: stable, solo maintainer |
| **Weighted total** | | **63** | **51** | atopile leads on the heavily-weighted authoring/seam rows |

(atopile = 5·3+4·3+4·3+1·2+4·2+4·2+3 = 63; SKiDL = 2·3+2·3+4·3+5·2+3·2+4·2+3 = 51.)

## Why atopile wins for authoring (the load-bearing reasons)

1. **It gives the hardest seam check for free.** Parametric power-domain
   compatibility is caught by the constraint solver (Fault 1 → build fails). That is
   the expensive check; the I2C topology rules we'd build are cheap (proven: ~150 lines).
2. **Typed `.ato` is a safer LLM target.** The orchestrator emits typed blocks; the
   solver *rejects* a miswired voltage domain at compile time. This directly enforces
   the DESIGN.md principle that "the LLM never emits raw connectivity that bypasses
   validation." SKiDL's bare nets give no such compile-time guardrail.
3. **Manufacturable passives for free** (auto-picked to real LCSC MPNs).

## Where atopile is weak — and why it doesn't change the decision

- **ICs don't auto-resolve** (LDO/EEPROM fell out of the BOM; pinning needs an
  authored component definition via `ato create part`). But this is **intrinsic
  verified-block work in any substrate** — and `ato create part` yields real LCSC
  MPNs + footprints + pinmaps, i.e. it's the block-library pipeline we must build
  regardless. SKiDL "wins" here only by naming a generic KiCad symbol with no MPN.
- **No SPICE** — handled by the **ngspice (BSD) harness** we already built; keeping
  SPICE external is what the licensing analysis wanted anyway.
- **Version churn** — atopile ≥0.13 requires Python 3.14 (only at RC; its CLI
  crashed on 3.14.0rc2). **Mitigation: pin atopile 0.12.5 on Python 3.13** (today's
  known-good, used throughout the spike) and track the 3.14 line until stable.

## What the spike proved (acceptance criteria, SPIKE.md §6)

| # | Criterion | Status |
|---|---|---|
| 1 | Both substrates emit netlist + BOM | ✅ atopile (passives→MPN) · SKiDL (full netlist incl. real ICs) |
| 2 | Verified-block contract expressible | ✅ typed in atopile; manual in SKiDL — gap documented |
| 3 | Seam-validator catches all 3 faults, passes correct | ✅ `seam_validator.py` — exact, no false positives |
| 4 | PySpice DC op-point on the rail | ✅ via ngspice (PySpice dropped); rail=3.295V, pull-up=0.701mA |
| 5 | atopile picks passives to real LCSC parts | ✅ e.g. `C25744`, `C25900` |
| 6 | Whole flow driven programmatically / CLI | ✅ `ato build`, `python …` |
| 7 | Scorecard → decision | ✅ this memo |

## Recommended architecture (evidence-backed)

```
  NL spec ─► LLM orchestrator ─► typed .ato blocks ─► atopile (compile + solve)
                                       │                       │ catches power-domain seam
                                       ▼                       ▼
                            verified-block library      seam_validator (I2C/topology rules)
                            (authored IC components,            │
                             real LCSC MPNs)                    ▼
                                       └────────► ngspice (BSD) electrical sanity
                                                        │
                                                        ▼
                                          validated schematic + netlist + BOM
```

## Where effort goes next (the actual moat)

The validator is done-in-principle. The expensive, defensible work — confirmed by
both this spike and [`RESEARCH.md`](./RESEARCH.md) §3 — is the **verified-block /
IC part-data library**: authoring real IC components (footprints, pinmaps,
addresses, electrical limits) with provenance. That is the moat; the substrate and
validator are now de-risked enough to build on.

### Concrete next steps
1. **Pin the toolchain** (atopile 0.12.5 / Python 3.13) in a setup script.
2. ✅ **DONE — authored the first real verified IC blocks** via `ato create part`
   (AMS1117-3.3 LDO `C6186`, AT24C256 EEPROM `C6482`), wrapped with typed interfaces
   in `spike/atopile/verified_slice.ato`. **The BOM now resolves both ICs with real
   MPNs** (closing the Step-1 gap). Finding: atopile won't infer the I2C address from
   pins (i2c-tree stays empty) → **the block contract must carry address as explicit
   metadata** (the seam-validator already consumes it).
3. **Formalize the block contract** as a schema (ports, params, invariants,
   validation metadata, bound MPN, **I2C address**) — wire `seam_validator.py` to
   consume it directly from authored blocks.
4. **Then** start the LLM orchestrator against the typed `.ato` target.

> Risks #2 (monetization) and #3 (data moat) remain as scoped in
> [`BUSINESS.md`](./BUSINESS.md) / [`RESEARCH.md`](./RESEARCH.md); this memo closes
> the substrate/validator question under Risk #1.
