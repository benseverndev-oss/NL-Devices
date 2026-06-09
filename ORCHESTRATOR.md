# Orchestrator Prototype — NL → Validated Design

> The payoff milestone (DECISION.md step #4): a natural-language spec becomes a
> design by **composing pre-verified blocks**, gated by the seam-validator.
> Status: **prototype running** (`spike/orchestrator.py`).

## The loop (now closes in a manufacturable BOM)

```
  spec ─► Planner ─► slice ─► validate ─► codegen ─► ato build ─► BOM (real LCSC MPNs)
            ▲                    │ gate                  │
            pluggable            └ REJECT unsafe         └ verified_lib.ato modules
            (Heuristic | LLM seam, enum-constrained)
```

The architecture principle from [`DESIGN.md`](./DESIGN.md) made real: the planner
**selects and wires** blocks from the closed verified-block catalog
([`spike/blocks/*.yaml`](./spike/blocks)) — it never synthesises parts — and the
deterministic [`seam_validator`](./spike/seam_validator.py) **gates** the result.

## What it does today (runs without any API key)

`python3 spike/orchestrator.py` on three specs:

| Spec | Composed | Verdict |
|---|---|---|
| "MCU that logs **temperature** to **memory** over I2C" | LM75 (0x48) + EEPROM (0x50) + power + mcu | ✅ PASS |
| "MCU with **two** EEPROM chips" | EEPROM 0x50 + EEPROM 0x51 (distinct) | ✅ PASS |
| "MCU with **three** EEPROM chips" | only 2 distinct addresses exist → 3rd reuses 0x50 | ⛔ **REJECTED** (address collision) |

The third case is the point: when composition can't be done safely, **the validator
gate rejects it** rather than shipping a broken board. Every block selected is a
real, orderable part (`C6186`, `C477979`, `C6482`).

## The loop ends in a real BOM (`--build`)

`python3 spike/orchestrator.py --build` (or `codegen.py`) takes each passing design
all the way: the verified blocks are authored `.ato` modules
([`atopile/verified_lib.ato`](./spike/atopile/verified_lib.ato)); `codegen.py` emits
the top-level `App` from the slice and runs `ato build`. The temperature-logger spec
yields a manufacturable BOM:
```
U1, SOT-223-3, AMS1117-3.3,      C6186     (LDO)
U2, SOIC-8,    LM75AIMX/NOPB,    C477979   (temp sensor @0x48)
U3, SOIC-8,    AT24C256C-SSHL-T, C6482     (EEPROM @0x50)
R1,R2 4.7kΩ C25900 · C1/C2/C3 decoupling — all real LCSC MPNs
```
**NL → orderable board, gated by validation.** Codegen composes pre-verified block
modules; it never invents connectivity beyond wiring typed ports.

## The LLM seam (how a model plugs in)

`LLMPlanner` builds the catalog prompt and an `emit_plan` tool whose `block_id` is an
**`enum` of catalog ids** — so the model *cannot* name a part outside the verified
library (anti-hallucination), and whatever it emits still passes through the
validator gate. Two safety layers, neither trusting the model:

```json
"block_id": {"type": "string",
             "enum": ["mcu_i2c_controller","power_3v3_ldo",
                      "sensor_eeprom_24c256","sensor_eeprom_24c256_b","sensor_temp_lm75"]}
```

`plan(spec, lib, feedback=…)` already accepts validator feedback, so the LLM
retry-on-failure loop is wired; it activates when a `call_model` client is injected
(no usable API key in this environment, so the prototype runs the heuristic planner).

## Scope

**In:** NL → block selection + wiring → seam-validation gate; pluggable planner with
a deterministic implementation and a fully-specified, constrained LLM seam; real
parts; the reject-unsafe-design behaviour.

**Out (next):**
1. **Real LLM planner** — inject an Anthropic `call_model`; run NL specs through the
   model with the enum-constrained tool + validator-feedback retry loop.
2. ✅ **DONE — atopile codegen** (`spike/codegen.py`): emits `App.ato` from the slice
   and `ato build`s to a manufacturable BOM. `orchestrator.py --build` runs the whole
   NL → BOM loop.
3. **Richer library + auto-addressing** — more block types; auto-assign I2C addresses
   from each part's strappable range instead of fixed per-block.
4. **Power/▸electrical checks in the loop** — fold the ngspice rail check
   ([`rail_check.py`](./spike/skidl/rail_check.py)) into the gate.

## Why this matters

This is the first time the **"NL → validated design" loop closes**. It demonstrates
the whole thesis in miniature: the LLM is a constrained *composer*, the moat is the
*verified-block library*, and *validation is the product* — an unsafe design is
rejected, not shipped. Everything downstream (manufacturability, monetisation) builds
on this gated loop.

## Reproduce
```bash
cd spike && python3 orchestrator.py            # compose + gate (no atopile)
cd spike && python3 orchestrator.py --build    # NL -> ... -> manufacturable BOM
cd spike && python3 codegen.py                 # one spec, full codegen + build
```
