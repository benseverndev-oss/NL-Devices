# Gap Audit — Distance to the Ultimate Goal

> Honest assessment of what stands between the current repo and the stated goal.
> Method: every spike component was **run**, not just read — claims below are tagged
> ✅ *verified by execution*, ⚠️ *runs but weaker than the docs imply*, or ❌ *absent*.
> Severity: 🔴 blocks the goal · 🟠 major · 🟡 secondary. Companion to
> [`DECISION.md`](./DECISION.md), which closed the substrate/validator question (Risk #1).

---

## 1. The goal, restated

From [`README.md`](./README.md) / [`DESIGN.md`](./DESIGN.md):

> **Natural language → _validated_ schematic/netlist + BOM → (eventually) a routed PCB
> exportable to fab.** An LLM orchestrator **composes pre-verified blocks** (never
> synthesises), validated against a **ground-truth component database**, with
> deterministic compile + verification. *Validation is the product; NL is the interface.*

Four load-bearing nouns: **NL interface**, **verified-block library**, **validation
engine**, **ground-truth part DB** — plus the "eventually" tail (**layout → fab**)
and the business model that pays for it.

---

## 2. What is actually done (credit where due)

The Phase-0 spike is real and closes a miniature loop — confirmed by running it:

- ✅ `seam_validator.py` catches all 3 self-injected seam faults, no false positives.
- ✅ `block_contract.py` schema-validates 4 authored blocks and composes a slice.
- ✅ `orchestrator.py` (heuristic planner) composes specs, auto-assigns I2C
  addresses, and **rejects** an address-space-exhausted design via the gate.
- ✅ `orchestrator.py --build` runs the full **NL-ish → compose → gate → `ato build`**
  loop and emits a genuinely manufacturable BOM with real LCSC MPNs
  (`C6186` LDO, `C477979` LM75, `C6482` EEPROM ×3, real passives) — networked
  part-pick against LCSC works in this environment.

**This de-risked Risk #1**: the seam-validation moat is small, deterministic, and
real, and atopile pre-builds the parametric power-domain check for free. That result
holds. The gaps below are about the *other three* nouns and the "eventually" tail —
most of which the docs describe as further along than the code is.

---

## 3. The headline gap: three "done" claims are aspirational

These are the most important findings because they're where docs and running code
diverge — correcting them reframes how far along the project really is.

| Claim in docs | What the code actually does | Severity |
|---|---|---|
| "**NL → design**" / "the LLM is a constrained composer" | The planner that runs is `HeuristicPlanner` — a **hard-coded keyword router** (`CAPS` maps only `temperature` and `eeprom`; `QTY` maps number-words). There is **no NL understanding**. Any spec outside that tiny vocabulary silently yields just power+mcu. | 🔴 |
| "LLM retry-on-failure loop is **wired**" | `LLMPlanner.call_model` is `None` → `plan()` raises; **the LLM has never planned anything**. `run()` calls `planner.plan(spec, lib)` with no `feedback` and **never loops** — the retry is an unused parameter, not a wired loop. The model is only ever used to *print its tool schema*. | 🔴 |
| "**electrical gate** with ngspice teeth" | ngspice *is* invoked, but the decks are an **ideal source behind 0.1 Ω into a resistor** and a **resistor divider** — i.e. Ohm's-law arithmetic dressed as SPICE. The only failure paths are explicit `max_current_ma` / `>3 mA` comparisons that need no simulator. No LDO model, dropout, transient, thermal, or decoupling check. | 🟠 |

Net: the project has a **proven validator** and a **real compile-to-BOM path**, but
the **"NL" leg — the product's namesake — is essentially unbuilt**, and the
electrical leg is a placeholder.

---

## 4. Gap-by-layer

### 4a. NL interface / orchestrator — 🔴
- ❌ No real LLM integration. Needs an injected `call_model` (Anthropic), the
  enum-constrained `emit_plan` tool exercised against a real model, and an **actually
  iterating** validator-feedback retry loop (currently absent in `run()`).
- ❌ No evaluation of NL→plan quality: no spec corpus, no measure of how often the
  model picks/wires correctly, no handling of ambiguous or out-of-catalog requests.
- ⚠️ The heuristic router is fine as a deterministic fallback but must not be
  mistaken for the product.

### 4b. Verified-block library — 🔴 (the acknowledged moat, still tiny)
- ❌ **No real MCU.** `mcu_i2c_controller` is `bound_part: null` — literally a
  decoupling cap + two pull-up resistors. **The flagship "sensor node" has no brain;
  the emitted board would not function.** This is the single most concrete hardware gap.
- ⚠️ **4 blocks, 1 bus type (I2C), 1 power topology (one LDO).** No SPI/UART, no
  buck/boost, no battery/charging, no USB, no connectors, no analog, no crystal/reset/
  programming header — none of the parts a real board needs around the MCU.
- ❌ **Datasheet → structured-data extraction pipeline = 0.** Named as core BUILD IP
  in DESIGN §4; blocks were hand-authored via `ato create part` + hand-typed YAML. No
  extraction, no provenance, no human-in-the-loop review tooling.

### 4c. Validation engine depth — 🟠
- ⚠️ Only 3 topological + 2 toy-electrical checks, all I2C/rail-specific.
- ❌ No pin-level ERC on the *composed* design in the pipeline (SKiDL ERC was a
  one-off in step 2, never integrated into the gate).
- ❌ No checks for max ratings (Vds/I/P dissipation), reverse polarity, decoupling
  adequacy, thermal, bus capacitance/speed vs. participants, mechanical/footprint fit.
- ❌ **Validator only ever tested on faults its authors designed it to catch.** No
  external/adversarial corpus, no measured false-negative rate on real buggy designs.
  The "trust layer" claim needs evidence beyond 3 hand-picked faults.

### 4d. Ground-truth component DB — 🔴 (architecturally central, absent)
- ❌ **The "ground-truth part DB" in the DESIGN architecture diagram does not exist.**
  Validation runs against **hand-typed YAML** (voltage, tolerance, address,
  current_ma). A typo in a block's YAML is undetectable — there is no ground truth to
  check it against, which undercuts "validated against a ground-truth database."
- ❌ No jlcparts ingest, no stock/price feed, no ratings DB, no provenance store.
- ⚠️ Part-pick requires **network at build time** (LCSC) → non-reproducible/CI-fragile;
  no offline cache or pinned parts snapshot.

### 4e. Layout → routing → fab export (the "eventually") — 🟠 (unstarted, but in-goal)
- ❌ `ato build` emits a `.kicad_pcb` with components but **no placement/routing**.
- ❌ No autorouter integration (DESIGN says *complement* Quilter — no integration).
- ❌ No fab export (Gerbers, JLC/PCBWay order API, assembly). The README's "routed PCB
  exportable to fab" is entirely future work.

### 4f. Product / delivery — 🟡
- ❌ No UI, API service, persistence, accounts, or project/versioning — it's a set of
  CLI scripts. Intentional for now, but it is distance to a *product*.

### 4g. Engineering hygiene / reproducibility — 🟡
- ❌ No CI, no test runner (scripts self-assert via `SystemExit`; no pytest), no
  SessionStart hook to keep the toolchain green on web sessions.
- ❌ Toolchain **not pinned** (`ato.yaml` says `>=0.12.0`; DECISION's own step 1 "pin
  atopile 0.12.5 / Python 3.13 in a setup script" is **not done**). No root deps
  manifest; `pyyaml` is assumed preinstalled.

### 4h. Business / monetization — 🟠 (strategy only, unvalidated)
- ❌ Risk #2 (will the wedge customer pay for a guarantee?) and Risk #3 (fab wholesale
  margin exists? data-moat legality?) remain **exactly as scoped** — no customer
  discovery, no fab-margin confirmation, no supplier-pays pilot. All of BUSINESS.md is
  hypothesis.

---

## 5. Prioritized path to close the gaps

Ordered by *unlocks-the-most* / *cheapest-proof-first*:

1. **Make "NL" real (🔴, small).** Inject an Anthropic `call_model` into `LLMPlanner`,
   run the existing enum-constrained tool against a real model, and **actually
   implement the feedback→retry loop** in `run()`. Build a 15–20 spec eval set and
   report plan-correctness. *This is the cheapest way to turn the namesake from
   aspiration into evidence.*
2. **Author one real MCU block (🔴).** A concrete microcontroller (e.g. an
   STM32/ESP/RP2 with real LCSC part, power, decoupling, reset, programming header).
   Until this exists, no emitted board functions — and it exercises whether the block
   pattern scales beyond passives+EEPROM.
3. **Stand up a real part-data layer (🔴).** Ingest jlcparts; back each block's YAML
   numbers with a ground-truth lookup so a wrong rating/address/footprint is *caught*,
   not trusted. Add an offline/pinned snapshot for reproducible CI builds.
4. **Pin the toolchain + add CI (🟡, trivial).** Setup script (atopile 0.12.5 / Py
   3.13), a SessionStart hook, and a CI run of the four spike scripts. Closes
   DECISION step 1 and stops bit-rot.
5. **Deepen + adversarially test the validator (🟠).** Add real-rating/ERC checks and
   a *third-party* corpus of known-bad designs to measure false negatives — the only
   way the "trust" claim earns its keep.
6. **Replace SPICE theater with a real model (🟠).** A genuine LDO/dropout + bus-
   capacitance simulation, or drop the ngspice framing and call the checks what they
   are (analytic limits).
7. **Spike one fab-export path (🟠).** Gerbers + a single fab order API — smallest
   step toward the "eventually" tail and a prerequisite for the assembly-order
   business model.
8. **Run the cheapest business test (🟠):** 5–10 customer-discovery calls on respin
   WTP and one fab partner conversation on wholesale margin — the two unproven
   assumptions the whole revenue model rests on.

---

## 6. One-paragraph bottom line

The spike honestly de-risked the **validator** and proved a **compile-to-manufacturable-
BOM** path — that part is real and runs. But three of the goal's four pillars are
still largely unbuilt: the **NL interface is a keyword router with the LLM never
invoked**, the **ground-truth part DB doesn't exist** (validation trusts hand-typed
YAML), and the **verified-block library has no functional MCU**. The "eventually"
tail (routing → fab) and the business assumptions are untouched. None of this
contradicts the strategy — it means the project is at *"validator proven, product not
yet started."* The highest-leverage next move is the cheapest: wire a real model into
the existing constrained seam and author one real MCU block, turning the headline
loop from a demo into something that produces a board that would actually work.
