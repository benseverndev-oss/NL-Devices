# Phase-0 Spike — Vertical Slice: Verified Blocks + Seam Validation

> Scopes the first build. This is the **prerequisite everything hinges on**: per
> [`DESIGN.md`](./DESIGN.md) §6 (Risk #1) and [`BUSINESS.md`](./BUSINESS.md), all
> three real revenue lines are gated by a **trustworthy validator**. This spike
> proves (or kills) that the verified-block + seam-validation thesis is real and
> measures how much we get for free vs. must build.
>
> Substrate facts are sourced in [`RESEARCH.md`](./RESEARCH.md) §1 and a focused
> atopile/SKiDL capability pass (2026-06-08).

---

## 1. Spike goal (one sentence)

Express **3 verified subcircuit blocks** with explicit typed port contracts,
**compose** them into one regulated-rail + I²C-sensor slice, and have a
**validation layer catch deliberately-injected seam faults** before emitting a
netlist + BOM — done in **both atopile and SKiDL** to pick the substrate.

### Explicit non-goals (out of scope for this spike)
- ❌ The LLM orchestrator (we author the slice by hand; LLM comes after the substrate is chosen).
- ❌ PCB layout / autorouting (DESIGN.md says complement Quilter later).
- ❌ Breadth of part coverage, the full block library, or the datasheet-extraction pipeline.
- ❌ Any UI. Everything is CLI / scriptable.

---

## 2. The target slice (a minimal real IoT sensor node)

```
   5V in ──►[ Power block ]──► 3V3 rail ──┬──►[ MCU block ]
                                          │        │ I²C
                                          └──►[ Sensor block ]
```

Three blocks — small enough to finish in days, real enough to exercise every seam
type we care about:

| Block | Function | Ports (typed) |
|---|---|---|
| **Power** | 5V → 3V3 LDO/regulator + in/out caps (e.g. AMS1117-3.3) | `pwr_in: ElectricPower(5V)`, `pwr_out: ElectricPower(3V3)`, `gnd` |
| **MCU** | microcontroller, I²C master | `pwr: ElectricPower(3V3)`, `i2c: I2C`, `gnd` |
| **Sensor** | I²C temp/humidity sensor (e.g. SHT3x) | `pwr: ElectricPower(3V3)`, `i2c: I2C` (`requires_pulls`), `gnd` |

---

## 3. What a "verified block" is (the contract to prototype)

This is the core artifact. A block is **not** just a subcircuit — it carries a
machine-checkable contract:

| Field | Meaning | atopile mechanism | SKiDL mechanism |
|---|---|---|---|
| **Identity** | name, version, function | `module` + package release | `@SubCircuit` fn + module ver |
| **Typed ports** | structured interfaces, not bare nets | `ElectricPower`, `I2C`, `ElectricLogic.reference` (voltage domain) | `Interface(...)` bundle *(untyped — we add type tags)* |
| **Parameters** | values w/ ranges + tolerance | native (`10kohm +/- 5%`) | plain attrs *(we add ranges)* |
| **Invariants** | assertions that must hold | `assert vin within 4.5V to 5.5V` | `erc_assert(...)` / custom |
| **Bound part** | resolved MPN + provenance | `has_part_picked` (JLCPCB id) | manual `Part(...)` + our metadata |
| **Validation metadata** | which checks ran, SPICE ref | (we attach) | (we attach) |

**Finding that matters:** atopile's typed interfaces (`ElectricPower` voltage
domains, `I2C.requires_pulls`, recursive `~`) already encode ~half of this contract
*natively*. SKiDL's `Interface` is just named nets — we'd add the type layer
ourselves. This is the single biggest differentiator the spike must weigh.

---

## 4. The seams to validate (and the injected faults)

The TypedSchematics open problem (arXiv 2509.14576) is exactly "how do blocks
connect correctly?" The spike makes that concrete: build the **correct** slice,
then inject **3 faults** and require the validator to flag each.

| Seam | Rule | Injected fault → must be caught |
|---|---|---|
| **Power domain** | rail voltage ∈ each consumer's tolerated supply range | Feed the 3V3 MCU from a 5V rail → **domain mismatch** |
| **I²C bus** | pull-ups present; addresses unique; bus freq ≤ min(participants) | Drop the `requires_pulls` pull-ups → **missing pull-ups**; duplicate sensor address → **address collision** |
| **Completeness** | every required port connected; power + gnd present | (baseline: no floating power/ground) |
| **Electrical sanity** | DC operating point within tolerance | regulator rail Vout asserted ≈ 3.3V ± tol via PySpice `.operating_point()` |
| **Pin-level ERC** | no unconnected pins / drive conflicts | SKiDL `ERC()` on the composed netlist |

**Validation layer = typed-interface checks (atopile) + a thin custom seam-checker
(bus rules, domain compat) + SKiDL `ERC()` + a PySpice DC op-point sanity check.**

---

## 5. The bake-off — decision scorecard

Run the *same* slice through both. Score each dimension; the weighted total picks
the substrate (or a hybrid).

| Dimension | Weight | atopile (hypothesis) | SKiDL (hypothesis) |
|---|---|---|---|
| **Port-contract expressiveness** (typed seams) | ★★★ | Strong — typed interfaces native | Weak — untyped nets, we build it |
| **Seam-check leverage** (validation for free) | ★★★ | Strong — constraint solver + `assert` | Medium — `ERC()` is pin-level only |
| **Electrical / SPICE validation** | ★★ | None built in | Strong — native PySpice/ngspice |
| **Part resolution + manufacturability** | ★★ | Strong — JLCPCB auto-picker + BOM | Weak — manual symbol naming |
| **Programmatic drivability** (future LLM gen) | ★★★ | Medium — LLM emits `.ato` text (typed guardrails help) | Strong — pure Python, easy to generate/call |
| **Extensibility for our custom validator** | ★★ | Medium — DSL, hook `check_design` stages | Strong — it's just Python |
| **Maturity / bus-factor** | ★ | YC co., ~3.4k★, active | Solo maintainer, mature |

> **Going-in hypothesis (to confirm or refute):** adopt **atopile as the authoring
> substrate** (typed interfaces ≈ free seam-validation foundation + JLCPCB picker +
> manufacturing artifacts), and use **SKiDL+PySpice as a complementary electrical-
> validation harness** on the analog blocks. The spike exists to test this, not
> assume it — especially the "programmatic drivability" row, which the LLM
> orchestrator will live or die on.

---

## 6. Acceptance criteria (spike passes iff all hold)

1. ✅ Both substrates emit a **valid netlist + BOM** for the composed 3-block slice.
2. ✅ The **verified-block contract** (§3) is expressible in each substrate; gaps documented.
3. ✅ The **seam-validator catches all 3 injected faults** (domain mismatch, missing
   pull-ups, address collision) **and passes the correct design** (no false positives).
4. ✅ A **PySpice DC op-point** check asserts the 3V3 rail within tolerance.
5. ✅ atopile's **part-picker resolves passives to real JLCPCB parts**; BOM carries MPNs.
6. ✅ The whole flow is **driven programmatically/CLI** (precondition for LLM orchestration).
7. ✅ A filled-in **scorecard (§5)** yields a substrate decision with rationale.

---

## 7. Plan (≈1–2 week spike)

| Step | Work | Output |
|---|---|---|
| 0 ✅ | Env: install atopile, SKiDL, ngspice; reproduce each tool's hello-world — **DONE, all green** (see [`spike/README.md`](./spike/README.md)) | green baseline |
| 1 ✅ | Implement the 3 blocks + compose, in **atopile** (typed interfaces, `assert` invariants, `ato build`) — **DONE** ([`spike/atopile/sensor_node.ato`](./spike/atopile/sensor_node.ato); results in [`spike/README.md`](./spike/README.md)) | `.ato` slice + KiCad/BOM |
| 2 | Implement the 3 blocks + compose, in **SKiDL** (`@SubCircuit`, `Interface`, `ERC()`, `generate_netlist`) | Python slice + netlist |
| 3 | Build the **thin seam-checker** (power-domain compat, I²C bus rules, completeness) over each | validator module(s) |
| 4 | Inject the **3 faults**; confirm each is caught + correct design passes | fault-detection log |
| 5 | **PySpice** DC op-point on the power rail; assert Vout ≈ 3V3 ± tol | sim assertion |
| 6 | Fill the **scorecard**, write decision + the "build vs. free" boundary for the validator | decision memo |

---

## 8. Open unknowns to resolve in-spike (flagged by research)

**Resolved in Step 0:**
- ✅ **atopile emits a standalone netlist** (`divider.net`) + `.kicad_pcb` + BOM + reports.
- ✅ **PySpice is unusable** (v1.5 incompatible with ngspice 42, both shared & subprocess
  paths). **Decision: drive `ngspice` binary directly** (BSD; keeps SPICE out of the
  proprietary GPL surface). SKiDL's `skidl.pyspice` mode is consequently N/A.
- ✅ atopile **part-picker resolves real LCSC parts** (needs network).

**Resolved in Step 1:**
- ✅ **IC part-picking is NOT automatic** — generic `LDO`/`EEPROM` get "no picker, no
  footprint" and fall out of the BOM; only passives auto-resolve. Pinning a concrete
  IC requires a **component definition** (`ato create part`), not an `lcsc_id` on a
  generic instance. → "verified block w/ real IC" = real per-block work (the
  part-data moat bites here).
- ✅ **Typed composition + constraint solving + passive resolution work** end-to-end;
  typed seams (`SCL`/`SDA`/power rails) land in the netlist.

**Still open (steps 2–6):**
- **atopile:** scope of `POST_PCB`/`check_design` checks vs. KiCad DRC? (Med)
  `i2c-tree`/address checking needs concrete addressed devices (empty without picked ICs).
- **Cross-cutting (the moat measurement):** does typed-interface checking actually
  catch the injected seam faults (step 3–4), or is a **custom seam layer** still required?
- **Version:** spike used atopile **0.12.5**; pin/upgrade toward **0.14+** (typed-
  interface docs) before building the real blocks.
- **Licensing reminder:** ngspice is **BSD** (safe to embed); PySpice/KiCad-ERC are
  **GPLv3** — keep them as **external tools/harness**, not linked into proprietary core
  (per RESEARCH.md §4c). *Step 0 already followed this by dropping PySpice.*

---

## 9. Why this de-risks the whole company

The spike's fault-detection result is a direct read on **Risk #1** (is verified-block
+ seam-validation real, and how much is free vs. build?) and therefore on the
**moat**. Its scorecard picks the substrate the LLM orchestrator will target. And
per BUSINESS.md, a trustworthy validator is the **shared prerequisite** for the
guarantee model, the fab integration, and the supplier-pays engine — so this one
spike unlocks both the technical and the business path.

> Decisions feed back into [`DESIGN.md`](./DESIGN.md) §4 (substrate choice) and §7
> (next steps).
