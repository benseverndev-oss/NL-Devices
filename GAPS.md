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

> **Update (since this audit):** rows 1–2 are now addressed — `spike/llm_client.py`
> wires a real `claude-opus-4-8` planner into the seam and `run()` implements the
> actual feedback→retry loop, evidenced by `spike/eval_planner.py` (see §5 item 1).
> **Row 3 (electrical theatre) is now addressed too** ([`SPEC-SPICE.md`](./SPEC-SPICE.md)):
> the Ohm's-law-in-a-SPICE-costume decks are gone. `electrical.py` runs one **honestly
> analytic** check (LDO dropout margin) on the gate path, and `spike/spice_sim.py` adds
> **genuine ngspice `.tran` sims** (I2C RC rise time, rail droop under a load step) whose
> `--selftest` cross-checks the analytic `0.8473·R·C` limit to <5% and proves teeth both
> ways — run live in CI. The structural gaps in §4 still stand.

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

### 4b. Verified-block library — 🟠 (real MCU now landed; breadth still thin)
- ✅ **Real MCU landed.** `mcu_i2c_controller` is now an **STM32F103C8T6** (LQFP-48,
  LCSC `C8734`) with full support circuitry — all VDD/VBAT/VDDA decoupling, the NRST
  reset RC, the BOOT0 strap, and I2C1 (PB6/PB7) bus pull-ups — authored in
  `verified_lib.ato` and resolving to a real MPN in the BOM (`spike/README.md`). The
  flagship sensor node now has a **brain**; the emitted board would function.
- ⚠️ **4 blocks, 1 bus type (I2C), 1 power topology (one LDO).** No SPI/UART, no
  buck/boost, no battery/charging, no USB, no connectors, no analog, no crystal/reset/
  programming header — none of the parts a real board needs around the MCU.
- ❌ **Datasheet → structured-data extraction pipeline = 0.** Named as core BUILD IP
  in DESIGN §4; blocks were hand-authored via `ato create part` + hand-typed YAML. No
  extraction, no provenance, no human-in-the-loop review tooling.

### 4c. Validation engine depth — 🟠 (deepened 3→9 checks; representable FN rate now 0)
- ⚠️ Was 3 topological + 2 toy-electrical checks; **now 9 checks** — added
  `current-budget`, `i2c-reserved-addr`, `i2c-bus-timing` (RC rise-time + bus
  capacitance), `part-rail-rating` (ground-truth join), `power-connectivity` (every
  active device sits on a rail), and `i2c-multimaster` (one controller per bus), fed
  real data via `block_contract.build_design`.
- ❌ Still no pin-level ERC on the *composed* design (SKiDL ERC never wired into the gate).
- ⚠️ Still no decoupling adequacy, abs-max/reverse-polarity, or thermal checks — but
  these are **enumerated** as `NOT_MODELLED` (not expressible in today's data model)
  rather than unknown (see below).
- ✅ **Validator now adversarially tested with a measured false-negative rate.**

> **Update (since this audit):** [`SPEC-VALIDATOR-DEPTH.md`](./SPEC-VALIDATOR-DEPTH.md).
> `spike/validator_corpus.py` runs a labelled corpus through the gate: **9/9 covered
> faults caught, 0 false positives, and a published 0/9 = 0% false-negative rate** over
> all *representable* known-bad designs. CI gates on covered-fault regressions only, so
> the FN inventory is surfaced without making CI red for known gaps.
>
> **Post-roadmap:** all three representable FNs are now **built** and graduated from
> `bad_uncovered` to `bad_covered`, walking the FN rate 33% → 22% → 0%:
> `part-rail-rating` (joins the gate to the part DB — looks up each sink's ground-truth
> datasheet operating range via `build_design(..., snapshot)` and checks the rail the
> part *actually sees*; the orchestrator gate is now ground-truth-aware),
> `i2c-multimaster` (two controllers on one bus need arbitration the composition doesn't
> provide), and `power-connectivity` (an active device wired to no rail floats — every
> other check only reasons about the rails a block IS on, so it slipped past). **Still
> open:** 0% is over the *representable* corpus only — the honest frontier is the
> `NOT_MODELLED` list (decoupling, abs-max, pin-level ERC, thermal, bus-speed-vs-slowest)
> and a field-captured third-party corpus, which would likely push the rate back up.

### 4d. Ground-truth component DB — 🟠 (layer now exists for identity + key electricals)
- ❌ **(was 🔴)** The "ground-truth part DB" in the DESIGN architecture diagram did not
  exist. Validation ran against **hand-typed YAML** (voltage, tolerance, address,
  current_ma). A typo in a block's YAML was undetectable — no ground truth to check
  it against, undercutting "validated against a ground-truth database."
- ⚠️ Part-pick requires **network at build time** (LCSC) → non-reproducible/CI-fragile;
  the snapshot below is a step toward pinning *validation*, not yet the atopile build.

> **Update (since this audit):** the ground-truth layer is now built
> ([`SPEC-PARTDB.md`](./SPEC-PARTDB.md)). `spike/partdb.py` ingests sourced data per
> LCSC part (EasyEDA identity + exact package + stock; LCSC parametric attributes)
> into a pinned `spike/parts_snapshot.json` with full provenance; `spike/verify_parts.py`
> is an **offline CI gate** that checks every block's `bound_part` + declared
> electricals against it. **28 fields VERIFIED / 0 mismatch** across the 4 blocks, and
> a `--selftest` proves the gate catches a bogus LCSC code, wrong MPN/footprint, an
> LDO bound to the wrong-voltage part, an over-claimed current, and a supply outside
> the part's rating. **Still open:** I2C `address_base` + tolerances have no source yet
> (reported `UNVERIFIABLE`, not blessed); no price feed; the snapshot doesn't yet pin
> the `ato build` part-pick. This is why the row drops 🔴→🟠 rather than closing.

### 4e. Layout → routing → fab export (the "eventually") — 🟢 (routed + DRC-clean copper now exported)
- ✅ **The routing 🔴 is closed for the `verified` board** ([`SPEC-ROUTING.md`](./SPEC-ROUTING.md)).
  `ato build` → `spike/place.py` (courtyard-safe placement + board outline) →
  `pcbnew.ExportSpecctraDSN` → **headless freerouting** → `pcbnew.ImportSpecctraSES` →
  `kicad-cli pcb drc` → `kicad-cli` Gerber/drill export, run in CI on every push and
  **hard-gated: 0 unrouted nets + 0 DRC violations + format-valid copper layers**. The
  routed board (AMS1117 LDO + AT24C256 EEPROM + I2C, 7 footprints, 5 nets) produces real
  F.Cu/B.Cu/Edge.Cuts Gerbers + drill — no longer a placeholder.
- ✅ **Reference autorouter integrated** (freerouting), behind a Specctra `.dsn`/`.ses`
  seam where a production router (Quilter) swaps in — this is the DESIGN §4 reversal
  (AVOID → qualified BUILD).
- ✅ **Fab-export now carries real copper** ([`SPEC-FAB-EXPORT.md`](./SPEC-FAB-EXPORT.md) +
  `fab_export.build_routed_package`): the JLCPCB package's **BOM + CPL come from the routed
  board** (single source of truth) alongside the real `kicad-cli` Gerbers/drill; the
  bound ICs reconcile to the `verify_parts` snapshot (U1 AMS1117, U2 EEPROM) while
  atopile-picked passives are reported, not blessed.
- ⚠️ **Honest scope:** one board, one vertical, 2 layers; deterministic (not DFM-optimal)
  placement; `ato build`'s LCSC part-pick still hits the network (isolated in the `route`
  job). The original dry-run order path ([`SPEC-FAB-EXPORT.md`](./SPEC-FAB-EXPORT.md)) still
  never submits.

### 4f. Product / delivery — 🟡
- ❌ No UI, API service, persistence, accounts, or project/versioning — it's a set of
  CLI scripts. Intentional for now, but it is distance to a *product*.

### 4g. Engineering hygiene / reproducibility — 🟡
- ❌ No CI, no test runner (scripts self-assert via `SystemExit`; no pytest), no
  SessionStart hook to keep the toolchain green on web sessions.
- ✅ **Toolchain now pinned** (DECISION step 1). `scripts/setup.sh` / `setup.ps1`
  install **atopile 0.12.5 on Python 3.13** via `uv` + the spike Python deps;
  `ato.yaml` floor is `>=0.12.5`, `.python-version` pins 3.13. `scripts/check_toolchain.py`
  lints pin-consistency (offline CI step) and a `toolchain` CI job proves the install
  resolves. *Still open:* `pyyaml` version isn't hard-locked and there's no single
  root deps lockfile (setup installs `spike/requirements.txt`).

### 4h. Business / monetization — 🟠 (strategy only, unvalidated)
- ❌ Risk #2 (will the wedge customer pay for a guarantee?) and Risk #3 (fab wholesale
  margin exists? data-moat legality?) remain **exactly as scoped** — no customer
  discovery, no fab-margin confirmation, no supplier-pays pilot. All of BUSINESS.md is
  hypothesis.

---

## 5. Prioritized path to close the gaps

Ordered by *unlocks-the-most* / *cheapest-proof-first*:

1. ✅ **DONE (mechanism) — "NL" wired** ([`SPEC-NL-PLANNER.md`](./SPEC-NL-PLANNER.md)).
   `spike/llm_client.py` plugs an Anthropic `call_model` (`claude-opus-4-8`, forced
   `emit_plan` tool) into the seam; `run()` now implements the **real feedback→retry
   loop** (was an unused param); `spike/eval_planner.py` scores a 16-spec corpus —
   offline `100%` correctness / `0%` hallucination, layer-2 safety + attempt-≥2
   recovery checks, runnable in CI without a key (`--live` for the real model).
   **Caveat:** proves the *mechanism* on a 4-block catalog; a live run needs
   `ANTHROPIC_API_KEY`, and breadth (item 2) is what proves it *scales*.
2. ✅ **DONE — real MCU block authored.** `mcu_i2c_controller` is now a real
   **STM32F103C8T6** (`C8734`) with power/decoupling/reset/BOOT0/I2C — it resolves in
   a manufacturable BOM and proves the verified-block pattern scales past
   passives+EEPROM to a 48-pin IC. *Next breadth step:* a second power topology and a
   non-I2C bus, to stress the validator beyond one seam type.
3. ✅ **DONE (mechanism) — ground-truth part-data layer** ([`SPEC-PARTDB.md`](./SPEC-PARTDB.md)).
   `spike/partdb.py` ingests sourced data per LCSC part (EasyEDA + LCSC parametric
   table) into a pinned `spike/parts_snapshot.json` with provenance; `spike/verify_parts.py`
   is an **offline CI gate** that backs each block's YAML numbers with a ground-truth
   lookup so a wrong LCSC code / MPN / footprint / output-voltage / supply-range /
   over-claimed-current is **caught, not trusted** (28 fields verified, 6/6 injected
   faults caught). **Still open:** `address_base`/tolerance ground truth (no source yet
   → `UNVERIFIABLE`), price/stock feed depth, and pinning the *`ato build`* part-pick to
   the snapshot for fully offline builds.
4. ✅ **DONE — pin the toolchain + CI (🟡).** CI runs ngspice + the four spike
   scripts incl. the planner eval; **now also** `scripts/setup.sh`/`setup.ps1` pin
   **atopile 0.12.5 / Python 3.13** (DECISION step 1), `scripts/check_toolchain.py`
   lints pin-consistency offline, and a `toolchain` CI job proves the pinned install
   resolves. *Still open:* a single root deps lockfile / hard-locked `pyyaml`.
5. ✅ **DONE — deepened + adversarially tested the validator** ([`SPEC-VALIDATOR-DEPTH.md`](./SPEC-VALIDATOR-DEPTH.md)).
   Checks 3→**9** (`current-budget`, `i2c-reserved-addr`, `i2c-bus-timing`, and
   post-roadmap `part-rail-rating`, `power-connectivity`, `i2c-multimaster`);
   `spike/validator_corpus.py` **measures the false-negative rate: 9/9 covered faults
   caught, 0 false positives, 0/9 = 0% FN** over the representable corpus (walked 33% →
   22% → 0% as `part-rail-rating`, then `i2c-multimaster` + `power-connectivity` graduated
   from `bad_uncovered` to `bad_covered`; `part-rail-rating` also joined the gate to
   `verify_parts`, so it is ground-truth-aware). CI gates on covered-fault regressions.
   **Still open:** a *third-party* (field-captured) corpus, and the `NOT_MODELLED` faults
   today's data model can't express (decoupling, abs-max, pin-level ERC, thermal).
6. ✅ **DONE — replaced the SPICE theatre** ([`SPEC-SPICE.md`](./SPEC-SPICE.md)). Did
   both: the Ohm's-law decks are deleted; `electrical.py` runs an **honestly analytic**
   LDO dropout-margin check on the gate path, and `spike/spice_sim.py` adds **real
   ngspice `.tran` sims** (I2C rise time + rail droop under a load step) that have teeth
   and whose `--selftest` cross-checks the analytic `0.8473·R·C` limit to <5% (run live
   in CI). **Still open:** wire the proven droop sim into the gate (needs per-rail
   decoupling-cap data) and a load/thermal-dependent behavioural LDO model.
7. ✅ **DONE — fab-export path + the routing blocker closed** ([`SPEC-FAB-EXPORT.md`](./SPEC-FAB-EXPORT.md)
   then [`SPEC-ROUTING.md`](./SPEC-ROUTING.md)). The original spike emitted a JLCPCB package
   (real-LCSC BOM + CPL + format-valid Edge.Cuts Gerber + Excellon drill) + a **validated,
   dry-run** assembly-order payload (never submits). **The "real blocker" — routing — is now
   closed for the `verified` board:** a CI-gated pipeline (`place.py` + `route.py` +
   `kicad_specctra.py`) drives `ato build` → place → headless **freerouting** → DRC →
   `kicad-cli` Gerbers, **hard-gated on 0 unrouted + 0 DRC + format-valid copper**, and
   `fab_export.build_routed_package` folds the real copper + routed CPL into the package
   (BOM/CPL from the routed board; bound ICs reconcile to the snapshot). **The fuller
   `verified_mcu` board (real STM32F103C8T6 + LDO + EEPROM, 48-pin LQFP, 15 footprints) now
   BUILDS *and* ROUTES** to the same hard gate (0 unrouted / 0 DRC / format-valid copper),
   closing decision 0004's deferred follow-up. Two earlier autoroute attempts (CI #50/#51)
   proved a flat by-size grid is unroutable (freerouting thrashed ~1000 passes); the fixes:
   - **Block-cluster placement** — footprints carry `(property "atopile_address" "mcu.cap")`,
     so `place.py` groups each atopile block's parts contiguously around its IC. That keeps
     intra-block nets (power/decoupling/pull-ups) short; freerouting then converges in ~6
     passes / 1.6 GB (no GND/3V3 pours needed at this size).
   - **`solder_mask_bridge` excluded in `parse_drc`** — KiCad's
     `allow_soldermask_bridges_in_footprints` does **not** suppress `kicad-cli` DRC
     (confirmed: flag=`yes`, still reported), so the LQFP-48 0.5mm-pitch in-footprint mask
     bridges (a fab-capability matter, not a copper defect) are excluded; shorts/clearance/
     unrouted still gate.
   - **Vias** were never the blocker (the DSN defines `Via[0-1]_600:300_um`); freerouting is
     now wall-clock bounded so it can't run away.
   **Still open:** one vertical / 2 layers, deterministic (not DFM) placement, network
   part-pick at build; ground/power *pours* would be the next step for a denser board.
8. **Run the cheapest business test (🟠):** 5–10 customer-discovery calls on respin
   WTP and one fab partner conversation on wholesale margin — the two unproven
   assumptions the whole revenue model rests on.

---

## 6. One-paragraph bottom line

The spike honestly de-risked the **validator** and proved a **compile-to-manufacturable-
BOM** path — that part is real and runs. But three of the goal's four pillars are
still in progress: the **NL interface** now has a real, validator-gated LLM planner
(§5 item 1) but is proven only on a tiny catalog; the **ground-truth part DB now
exists** for identity + the key electrical numbers, with an offline CI gate (§5 item
3), though address/tolerance ground truth is still absent; and the **verified-block
library is thin** (now with a real MCU, but one bus type and one power topology). The "eventually"
tail (routing → fab) and the business assumptions are untouched. None of this
contradicts the strategy — it means the project is at *"validator proven, product not
yet started."* The highest-leverage next move is the cheapest: wire a real model into
the existing constrained seam and author one real MCU block, turning the headline
loop from a demo into something that produces a board that would actually work.
