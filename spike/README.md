# Spike Log

Progress against the [`SPIKE.md`](../SPIKE.md) plan. Step 0 = toolchain baseline;
Step 1 = the 3-block typed slice in atopile.

---

# Step 0: Toolchain Baseline (COMPLETE ✅)

Green baseline for the [`SPIKE.md`](../SPIKE.md) bake-off. Establishes that both
substrates and the SPICE-validation leg run end-to-end on a trivial circuit, and
records the environment decisions for the real slice (steps 1–6).

## Result — all three legs green

| Leg | Hello-world | Status | Proven capability |
|---|---|---|---|
| **atopile** | `atopile/` divider → `ato build` | ✅ | Compiles, **constraint solver** runs (post-design/post-solve checks), **JLCPCB part-picker resolves real parts**, emits netlist + BOM + `.kicad_pcb` |
| **SKiDL** | `skidl/hello_skidl.py` | ✅ | Builds circuit, **`ERC()` runs** (correctly flagged the open-ended divider nets), emits a KiCad netlist |
| **SPICE** | `skidl/ngspice_check.py` | ✅ | DC operating point via a **BSD-clean ngspice wrapper** (`V(MID)=2.500V`) |

Evidence — atopile picked a real part for the 10 kΩ 0402:
```
Designator,Footprint,Quantity,Value,Manufacturer,Partnumber,LCSC Part #
"R1, R2",R0402,2,10kΩ ±1% 62.5mW,UNI-ROYAL(Uniroyal Elec),0402WGF1002TCE,C25744
```

## Key findings (feed the bake-off + de-risk later steps)

1. **PySpice is dead for our purposes — confirmed empirically.** PySpice 1.5 (the
   last PyPI release, 2021; GitHub "git" is also 1.5) is **incompatible with ngspice
   42**: the shared-lib path errors `Unsupported Ngspice version 42 / Command 'run'
   failed`, and the subprocess path errors `Expected label Circuit instead of Note`
   (its raw parser chokes on ngspice 42's new header). This is exactly the
   maintenance risk flagged in [`RESEARCH.md`](../RESEARCH.md) §4c.
   → **Decision: drive the `ngspice` binary directly** (`ngspice_check.py`).
   ngspice is **BSD** (safe to embed) vs. PySpice's **GPLv3** — so this also keeps
   the SPICE leg out of our proprietary core, as DESIGN.md intended. SKiDL's own
   `skidl.pyspice` mode is therefore unavailable; not needed.

2. **atopile *does* emit a standalone netlist** (`build/builds/divider/divider/divider.net`)
   alongside `.kicad_pcb`, `divider.bom.csv`, and `*.variables.md` / `*.i2c_tree.md`
   reports. → Resolves the open question in SPIKE.md §8.

3. **atopile part-picking needs network** (hits the JLCPCB/LCSC parts DB; ~5 s for
   2 passives). Works under this environment's network policy. Plan for offline/CI.

4. **Substrate API specifics learned** (for writing the real blocks):
   - atopile `Resistor` exposes `unnamed[0]` / `unnamed[1]` (faebryk); `Electrical`
     and `Resistor` must each be `import`ed. Values are native: `10kohm +/- 5%`.
   - SKiDL needs KiCad symbol libs; we use the **monolithic** format (KiCad tag
     `8.0.0`), not GitLab master's new split `*.kicad_symdir/` layout.

5. **Version note:** atopile installed is **0.12.5** (latest is 0.15.7). Pin/upgrade
   deliberately before step 1 — newer syntax (typed interfaces docs) targets 0.14+.

## Reproduce

**Prereqs (Ubuntu 24.04):**
```bash
apt-get install -y ngspice libngspice0-dev        # ngspice 42 (BSD)
# KiCad symbol libs (monolithic 8.0.0 format) for SKiDL:
git clone --depth 1 --branch 8.0.0 \
  https://gitlab.com/kicad/libraries/kicad-symbols.git spike/kicad-symbols
```

**SKiDL + SPICE leg:**
```bash
cd spike/skidl
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt                   # skidl only (no PySpice)
export KICAD_SYMBOL_DIR=$PWD/../kicad-symbols KICAD8_SYMBOL_DIR=$PWD/../kicad-symbols
python hello_skidl.py        # -> divider.net + ERC
python ngspice_check.py      # -> V(MID)=2.5V  PASS
```

**atopile leg** (Python 3.12+, via `uv`):
```bash
uv python install 3.13
uv tool install atopile --python 3.13             # installs `ato`
cd spike/atopile && ato build                      # -> build/builds/divider/...
```

## Files (committed)
- `atopile/main.ato`, `atopile/ato.yaml` — the atopile divider + build config
- `skidl/hello_skidl.py` — SKiDL divider + ERC + netlist
- `skidl/ngspice_check.py` — **BSD-clean ngspice op-point primitive** (the SPICE
  leg the validator will reuse)
- `skidl/requirements.txt` — pinned deps (skidl only)

Generated dirs (`build/`, `elec/`, `.venv/`, `kicad-symbols/`) are git-ignored.

---

# Step 1: 3-Block Typed Slice in atopile (COMPLETE ✅, with findings)

`atopile/sensor_node.ato` — the SPIKE.md §2 slice: `5V →[PowerBlock]→ 3V3 →
[McuBlock] + [SensorBlock]`, composed over **typed** seams (`ElectricPower`,
`I2C`), built with `ato build -b sensor_node`.

The three blocks use the faebryk typed-interface library bundled with atopile:
`LDO` (PowerBlock), a custom I2C-controller (`McuBlock`: decoupling + bus
pull-ups), and a real `EEPROM` as the I2C peripheral (`SensorBlock`).

## What works (the moat-relevant wins)

| Capability | Evidence |
|---|---|
| **Typed-interface composition** | 3 blocks connect via `ElectricPower` + `I2C` with a single `~`; build's `post-design` + `post-solve` checks pass |
| **Constraint solver validates invariants** | `assert power_out.voltage within 3.3V +/- 5%` etc. solve; LDO `output_voltage` resolved to **`[3.234V, 3.366V]`** (= 3.3V ±2%) in the variable report |
| **Passive part-picking → real parts** | BOM picks real LCSC parts: `100nF C14663`, `1µF C52923`, `10µF C19702`, `4.7kΩ ×2 C25900` |
| **Typed seams appear in the netlist** | `sensor_node.net` (243 lines) carries real nets `SCL`, `SDA`, `power-VCC`, `power_in-VCC`, `GND` |
| **Standalone artifacts** | netlist + `sensor_node.bom.csv` + `*.variables.md` + `*.kicad_pcb` |

## Findings / limits (what this teaches us about the block library)

1. **IC part-picking is NOT automatic.** The generic `LDO` and `EEPROM` produced
   `WARNING: No pickers and no footprint` and are **absent from the BOM** — only
   passives auto-resolve. This confirms the RESEARCH.md flag (IC picker coverage
   = Low). *Net: a "verified block" with a real IC is real work, not a free pick.*
2. **Pinning a concrete IC requires a component *definition*.** Setting
   `regulator.lcsc_id = "C6186"` on a generic instance is rejected:
   *"You can't assign to a `component` with a specific part number outside of its
   definition."* → concrete parts must be authored as component blocks (or via
   `ato create part`, which fetches the footprint/pinmap). **This is precisely the
   per-block effort our library must own** — and it's where the datasheet/part-data
   moat (RESEARCH.md §3) actually bites.
3. **`i2c-tree` report is empty** — atopile's I2C semantic report needs concrete,
   address-bearing devices (the EEPROM didn't resolve to a part). Address/bus-rule
   checking therefore depends on real IC bindings, not just the typed interface.

## Implication for the bake-off

atopile delivers the **typed seams + constraint solving + passive resolution** for
free — a real head start on the seam-validation moat. The gap is **concrete IC
binding** (footprints, pinmaps, addresses), which is unavoidable block-library work
in *any* substrate. Step 3 will test whether atopile's typed checks catch the
injected seam faults, or whether we still need a custom seam layer.

## Reproduce
```bash
cd spike/atopile && ato build -b sensor_node    # atopile 0.12.5, Python 3.13
# artifacts in build/builds/sensor_node/
```

---

# Step 2: Same Slice in SKiDL (COMPLETE ✅) + the bake-off contrast

`skidl/sensor_node_skidl.py` — the identical slice as three `@subcircuit`
functions (`power_block` AMS1117-3.3, `mcu_block` I2C controller, `sensor_block`
24LC256 EEPROM), composed over shared nets, with `ERC()` + `generate_netlist()`.

## What works
| Capability | Evidence |
|---|---|
| **Real ICs in the netlist** | `sensor_node.net` (451 lines) contains **`AMS1117-3.3`** and **`24LC256`** as real components + full passive BOM — by naming the KiCad symbol directly (no picker needed) |
| **Pin-level ERC (controllable)** | first run flagged *"Insufficient drive current on net 5V/GND for POWER-IN pin"* (correct!); adding `net.drive = POWER` (≈ KiCad PWR_FLAG) → **"No errors or warnings"** |
| **Hierarchy preserved** | netlist carries `/power_block1/`, `/mcu_block1/`, `/sensor_block1/` sheets |
| **Seam nets** | `5V`, `3V3`, `GND`, `SCL`, `SDA` |

## The bake-off contrast (the core decision input)

| Dimension | atopile (step 1) | SKiDL (step 2) |
|---|---|---|
| **Typed port contract** (voltage domain, I2C) | ✅ native (`ElectricPower`/`I2C`) | ❌ bare nets — *we'd build the type layer* |
| **Constraint solving** (params + tolerance) | ✅ LDO out solved `[3.234V, 3.366V]` | ❌ none |
| **Pin-level ERC** | ⚠️ post-design checks (not classic pin ERC) | ✅ real, type-aware, controllable |
| **IC part resolution** | ❌ LDO/EEPROM **don't auto-pick** | ✅ name the symbol → IC in netlist |
| **Passive resolution** | ✅ auto-picked to **real LCSC MPNs** | ⚠️ manual (you give value + footprint) |
| **Manufacturing data (BOM w/ MPN)** | ✅ LCSC ids | ❌ generic KiCad symbols, no MPN |
| **SPICE** | ❌ none | ✅ via our direct-ngspice wrapper |

**Conclusion — the two are complementary, exactly as hypothesized.** atopile owns
the *typed seam + constraint solving + manufacturable passives* (the moat-relevant
authoring layer); SKiDL/KiCad owns *real IC definitions + pin-level ERC + SPICE*
(the electrical-validation layer). Neither alone is a complete substrate. The
**deciding test is Step 3**: does atopile's typed model actually *catch* the
injected seam faults? If yes, atopile-as-author + a SKiDL/ngspice validation
harness is the hybrid; if no, we build a custom seam layer regardless.

## Reproduce
```bash
cd spike/skidl && . .venv/bin/activate
export KICAD_SYMBOL_DIR=$PWD/../kicad-symbols KICAD8_SYMBOL_DIR=$PWD/../kicad-symbols
python sensor_node_skidl.py        # -> ERC clean + sensor_node.net
```

---

# Step 3+4: Seam-fault detection — THE MOAT MEASUREMENT (COMPLETE ✅)

The decisive test: inject the three SPIKE.md §4 seam faults and measure how many
atopile catches **natively** vs. how many we must build. Then prove our own
seam-validator catches all three.

## Part A — what atopile catches for free

Each fault is a build target in `atopile/sensor_node.ato` (modules
`AppFault1PowerDomain`, `AppFault2NoPulls`, `AppFault3AddrCollision`). Consumer
blocks declare their rail invariant (`assert power.voltage within 3.3V +/- 5%`).

| Fault | atopile native result | Caught? |
|---|---|---|
| **1. Power-domain mismatch** (MCU on 5V) | build **fails**: `Contradiction: Intersection of literals is empty — power5v.voltage [5V±5%] vs mcu.power.voltage [3.135V,3.465V]` | ✅ **YES** (constraint solver) |
| **2. Missing I2C pull-ups** | build **succeeds** — `requires_pulls` trait exists but is not enforced | ❌ no |
| **3. I2C address collision** (two peripherals @ 0x50) | build **succeeds** — address rules need concrete addressed devices | ❌ no |

**Finding:** atopile's typed model + constraint solver gives the **hardest** seam
check — parametric power-domain compatibility — *for free*. The I2C **topology**
rules (pull-ups, addresses) it does **not** enforce. So the seam-validation moat is
real but **partially pre-built by atopile** (the parametric third, the expensive one).

## Part B — our seam-validator catches all three

`seam_validator.py` (~150 lines, no deps, substrate-independent) runs over a typed
block-graph — the "verified block" contract from SPIKE.md §3 — and checks all three
seams. Output:

```
design                   power  pulls  addr   verdict
--------------------------------------------------------
correct                  ok     ok     ok      PASS
fault1_power_domain      FAIL   ok     ok      PASS
    └─ POWER: rail '5V' = [4.750V,5.250V] is outside 'mcu' accepted [3.135V,3.465V]
fault2_no_pullups        ok     FAIL   ok      PASS
    └─ I2C: bus 'i2c_bus' has no pull-up provider (SCL/SDA float)
fault3_addr_collision    ok     ok     FAIL    PASS
    └─ I2C: bus 'i2c_bus' address 0x50 collision ('sensor' and 'sensor_b')
--------------------------------------------------------
RESULT: PASS — validator caught exactly the injected faults
```

Each fault triggers **exactly** its intended check (no false positives) and the
correct design passes — SPIKE.md **acceptance criterion #3 met**.

## Verdict on the thesis (Risk #1)

**The seam-validation moat is real and cheap to build.** All three seam rules are
small, deterministic, and explainable; atopile already pre-builds the hardest
(parametric power domains) via its constraint solver. This is strong evidence for
the architecture: **atopile-as-author (typed seams + constraint solving) + a thin
custom seam-validator (I2C/topology rules) + the SKiDL/ngspice harness for
electrical sanity.** The expensive part is *not* the validator — it's the
verified-block library / IC part data (the Step-1 finding), which is where effort
should go.

## Reproduce
```bash
cd spike && python3 seam_validator.py                       # all 3 faults caught
cd atopile && ato build -b fault1   # atopile catches this (build fails by design)
                ato build -b fault2  # builds clean -> atopile misses (our checker catches)
                ato build -b fault3  # builds clean -> atopile misses (our checker catches)
```

---

# Next: First REAL verified IC blocks (the first moat brick) ✅

Per [`DECISION.md`](../DECISION.md), effort belongs in the verified-block / IC
part-data library. `atopile/verified_slice.ato` authors the first real ones.

## Pattern: atomic part + typed wrapper = a verified block

`ato create part --search <LCSC-id> --accept-single` fetches a real part (footprint,
symbol, pinmap, 3D model, `has_part_picked` MPN) as an **atomic component with bare
`signal` pins**. A *verified block* wraps that atomic part in a **typed module**
(`ElectricPower`/`I2C`) with **invariants** — so it is both **manufacturable** (real
MPN) and **seam-checkable** (typed ports). Two authored so far, in
`elec/src/parts/`:

| Block | Real part | LCSC | Footprint |
|---|---|---|---|
| `PowerBlock` | AMS1117-3.3 LDO | **C6186** | SOT-223-3 |
| `SensorBlock` | AT24C256C I2C EEPROM | **C6482** | SOIC-8 |

## Result: a fully manufacturable BOM (every line a real MPN)
```
Designator,Footprint,Quantity,Value,Manufacturer,Partnumber,LCSC Part #
C1,C0402,1,1µF…,Samsung,CL05A105KA5NQNC,C52923
C2,C0603,1,10µF…,Samsung,CL10A106KP8NNNC,C19702
C3,C0603,1,100nF…,YAGEO,CC0603KRX7R9BB104,C14663
"R1, R2",R0402,2,4.7kΩ…,UNI-ROYAL,0402WGF4701TCE,C25900
U1,SOT-223-3,1,,Advanced Monolithic Systems,AMS1117-3.3,C6186
U2,SOIC-8,1,,Microchip Tech,AT24C256C-SSHL-T,C6482
```
This closes the Step-1 gap (ICs absent from the BOM): with authored blocks, **both
ICs resolve with real MPNs**.

## Finding → a contract requirement
The **i2c-tree is still empty** even with a real addressed EEPROM: atopile can't
infer the I2C address from grounded A0/A1/A2 pins. So **the verified-block contract
must carry the I2C address as explicit metadata** (not inferred) — which is exactly
what `seam_validator.py` already consumes for the address-collision check. The
authored atomic part gives manufacturability; **our block contract supplies the
semantic metadata (address, supply range) the seam checks need.**

## Reproduce
```bash
cd spike/atopile
ato create part --search C6186 --accept-single   # LDO
ato create part --search C6482 --accept-single   # EEPROM
ato build -b verified                            # BOM has U1 C6186 + U2 C6482
```
