# SPI breadth Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the seam-validator a second bus (SPI) and prove it, then build and route a real STM32 + W25Q128 SPI board to fab-ready copper.

**Architecture:** Two independent, CI-gated workstreams, validator-first. **WS1** adds an *additive* `SPIBus` model + two SPI checks + a `power-connectivity` extension to the pure-Python validator, proven by the adversarial corpus (FN 0/9 → 1/13, publishing one new honest false-negative). **WS2** adds a real SPI flash part + an STM32-as-SPI-controller block, a new `spi_node` build target, and routes it at the hard 0/0 gate.

**Tech Stack:** Python 3.13 stdlib (validator), PyYAML (block contract — CI only), atopile 0.12.5 + KiCad 9 + freerouting 2.1.0 (WS2, CI only).

---

## ⚠️ Execution constraints (read first)

- **NEVER run heavy compute locally — it OOMs the owner's box.** No `ato build`, `pip install`, KiCad, or freerouting locally. **CI GitHub runners are the test runner** for anything needing those.
- **WS1 Tasks 1–5 run locally** — `seam_validator.py` and `validator_corpus.py` import only the stdlib. Run `python3 spike/validator_corpus.py` / `python3 spike/seam_validator.py` from the repo root. **Do NOT `pip install`.**
- **WS1 Task 6 + all of WS2 are CI-verified** — `block_contract.py` imports `yaml`, and WS2 needs the full toolchain. Author locally, push, watch CI.
- **Push** over the embedded-token URL (gh as `benzsevern`):
  `git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git <branch>`
- **Cadence:** branch off trunk `claude/brainstorm-idea-vegk59` → CI green → `gh pr merge <n> --squash --delete-branch`.
- **The proven `verified` (I2C) board and `McuBlock` must stay byte-for-byte unaffected** — SPI is additive everywhere.

---

## File Structure

| File | WS | Responsibility | Action |
|------|----|----------------|--------|
| `spike/seam_validator.py` | 1 | Validator model + `CHECKS` | **Modify** — add `SPINode`/`SPIBus`/`Design.spi_buses` + 2 checks + extend `power-connectivity` |
| `spike/validator_corpus.py` | 1 | Adversarial FN corpus | **Modify** — SPI baseline + 4 fixtures (3 covered, 1 published FN) |
| `spike/block_contract.py` | 1 | YAML block contract → `Design` | **Modify** — `spi` port schema + `type: spi` build branch + guard the I2C loop |
| `spike/blocks/mcu_spi_controller.yaml` | 1 | Abstract SPI-controller block | **Create** |
| `spike/blocks/spi_flash_w25q.yaml` | 1→2 | SPI flash block (abstract in WS1, bound in WS2) | **Create** (abstract) |
| `spike/slices/spi_node.yaml` | 1 | SPI slice composition | **Create** |
| `spike/atopile/elec/src/parts/Winbond_W25Q128.../**` | 2 | Real W25Q128 part (sym/fp/3D/.ato) | **Create** (in CI) |
| `spike/parts_snapshot.json` | 2 | Ground-truth part DB | **Modify** — ingest C97521 |
| `spike/atopile/verified_lib.ato` | 2 | Shared block lib | **Modify** — add `McuSpiBlock` + `SpiFlashBlock` (additive) |
| `spike/atopile/spi_slice.ato` | 2 | `spi_node` top App | **Create** |
| `spike/atopile/ato.yaml` | 2 | Build targets | **Modify** — add `spi_node` |
| `.github/workflows/ci.yml` | 2 | CI | **Modify** — route the `spi_node` board |

---

# Workstream 1 — validator learns SPI

**Branch:** `feat/spi-validator-breadth` (already exists; carries the spec).
**Tasks 1–5 verified locally** (stdlib); **Task 6 verified in CI** (needs `yaml`).

### Task 1: SPI model + corpus baseline (no checks yet)

**Files:** Modify `spike/seam_validator.py`, `spike/validator_corpus.py`

- [ ] **Step 1: Add the SPI dataclasses** to `seam_validator.py`, immediately after the `I2CBus` dataclass (before `Design`):

```python
@dataclass
class SPINode:
    block: str
    role: str                        # 'controller' | 'peripheral'
    chip_select: str | None = None   # CS net id (peripherals only)
    mode: int = 0                    # SPI mode 0..3 (CPOL/CPHA) — modelled, NOT yet checked


@dataclass
class SPIBus:
    name: str
    nodes: list[SPINode] = field(default_factory=list)
    speed_hz: int = 1_000_000
```

- [ ] **Step 2: Add `spi_buses` to `Design`** — add this field to the `Design` dataclass (after `buses`):

```python
    spi_buses: list[SPIBus] = field(default_factory=list)
```

- [ ] **Step 3: Add the SPI baseline + good case** to `validator_corpus.py`, after `good_baseline()`:

```python
def spi_baseline() -> sv.Design:
    """A clean SPI design: an MCU controller + one flash peripheral on its own CS."""
    return sv.Design(
        "good_spi_node",
        rails=[
            sv.PowerRail("5V", 5.0, 0.05, sinks=[("psu", 5.0, 0.20)]),
            sv.PowerRail("3V3", 3.3, 0.05, sinks=[("mcu", 3.3, 0.05), ("flash", 3.3, 0.05)]),
        ],
        spi_buses=[sv.SPIBus("spi_bus", nodes=[
            sv.SPINode("mcu", "controller", mode=0),
            sv.SPINode("flash", "peripheral", chip_select="cs0", mode=0),
        ])],
    )
```

- [ ] **Step 4: Register the good case** — add to the `CORPUS` list (in the `# good` block):

```python
    {"build": spi_baseline, "kind": "good", "expect": set(), "note": "SPI: MCU + flash, distinct CS"},
```

- [ ] **Step 5: Run — baseline stays green**

Run: `python3 spike/validator_corpus.py`
Expected: **exit 0**, `RESULT: PASS`. `good_spi_node` shows `ok (clean)` (no SPI checks exist yet, so nothing fires). The summary still reads `0/9 = 0%` (no bad SPI fixtures yet). `python3 spike/seam_validator.py` also still exits 0.

- [ ] **Step 6: Commit**

```bash
git add spike/seam_validator.py spike/validator_corpus.py
git commit -m "Add additive SPI model (SPINode/SPIBus/Design.spi_buses) + corpus baseline"
```

### Task 2: `spi-chip-select-unique` check (TDD)

**Files:** Modify `spike/seam_validator.py`, `spike/validator_corpus.py`

- [ ] **Step 1: Write the failing fixture** — add to `validator_corpus.py` (after `spi_baseline`):

```python
def _bad_spi_cs_collision() -> sv.Design:
    d = spi_baseline(); d.name = "bad_spi_cs_collision"
    d.rails[1].sinks.append(("flash_b", 3.3, 0.05))   # power it: single-fault
    d.spi_buses[0].nodes.append(sv.SPINode("flash_b", "peripheral", chip_select="cs0", mode=0))
    return d
```
and its `CORPUS` entry (in a new `# bad SPI, covered` block):
```python
    {"build": _bad_spi_cs_collision, "kind": "bad_covered", "expect": {"spi-chip-select-unique"},
     "note": "two SPI peripherals share CS cs0"},
```

- [ ] **Step 2: Run — red**

Run: `python3 spike/validator_corpus.py`
Expected: **exit 1**, `bad_spi_cs_collision` MISSED (expected `['spi-chip-select-unique']`, got nothing), `RESULT: FAIL`.

- [ ] **Step 3: Implement the check** — in `seam_validator.py`, after `check_i2c_multimaster` (or after `check_power_connectivity`):

```python
def check_spi_chip_select_unique(d: Design) -> list[str]:
    """Every SPI peripheral needs its own chip-select; two sharing a CS line would both
    respond at once. A peripheral with no CS is also flagged."""
    errs = []
    for b in d.spi_buses:
        seen: dict[str, str] = {}
        for n in b.nodes:
            if n.role != 'peripheral':
                continue
            if n.chip_select is None:
                errs.append(f"SPI: bus '{b.name}' peripheral '{n.block}' has no chip-select")
            elif n.chip_select in seen:
                errs.append(f"SPI: bus '{b.name}' chip-select '{n.chip_select}' shared by "
                            f"'{seen[n.chip_select]}' and '{n.block}'")
            else:
                seen[n.chip_select] = n.block
    return errs
```

- [ ] **Step 4: Register** — append to `CHECKS`:

```python
          ("spi-chip-select-unique", check_spi_chip_select_unique),
```

- [ ] **Step 5: Run — green**

Run: `python3 spike/validator_corpus.py`
Expected: **exit 0**. `bad_spi_cs_collision` shows `caught [spi-chip-select-unique]`; `good_spi_node` still `ok (clean)`; no other fixture perturbed.

- [ ] **Step 6: Commit**

```bash
git add spike/seam_validator.py spike/validator_corpus.py
git commit -m "Add spi-chip-select-unique check"
```

### Task 3: `spi-single-controller` check (TDD)

**Files:** Modify `spike/seam_validator.py`, `spike/validator_corpus.py`

- [ ] **Step 1: Failing fixture** — add to `validator_corpus.py`:

```python
def _bad_spi_no_controller() -> sv.Design:
    d = spi_baseline(); d.name = "bad_spi_no_controller"
    d.spi_buses[0].nodes = [n for n in d.spi_buses[0].nodes if n.role != "controller"]
    return d
```
CORPUS entry:
```python
    {"build": _bad_spi_no_controller, "kind": "bad_covered", "expect": {"spi-single-controller"},
     "note": "SPI bus with no master"},
```

- [ ] **Step 2: Run — red.** `python3 spike/validator_corpus.py` → exit 1, `bad_spi_no_controller` MISSED.

- [ ] **Step 3: Implement** — in `seam_validator.py`, after `check_spi_chip_select_unique`:

```python
def check_spi_single_controller(d: Design) -> list[str]:
    """Each SPI bus needs exactly one controller (master): zero = no master drives it,
    two = clock/CS contention."""
    errs = []
    for b in d.spi_buses:
        controllers = [n.block for n in b.nodes if n.role == 'controller']
        if len(controllers) != 1:
            errs.append(f"SPI: bus '{b.name}' has {len(controllers)} controllers "
                        f"({', '.join(controllers) or 'none'}); need exactly one")
    return errs
```

- [ ] **Step 4: Register** — append to `CHECKS`:

```python
          ("spi-single-controller", check_spi_single_controller),
```

- [ ] **Step 5: Run — green.** `python3 spike/validator_corpus.py` → exit 0; `bad_spi_no_controller` → `caught [spi-single-controller]`.

- [ ] **Step 6: Commit** (`"Add spi-single-controller check"`).

### Task 4: extend `power-connectivity` to SPI nodes (TDD)

**Files:** Modify `spike/seam_validator.py`, `spike/validator_corpus.py`

- [ ] **Step 1: Failing fixture** — add to `validator_corpus.py`:

```python
def _bad_spi_floating_power() -> sv.Design:
    d = spi_baseline(); d.name = "bad_spi_floating_power"
    # an SPI peripheral on no rail — its supply floats
    d.spi_buses[0].nodes.append(sv.SPINode("orphan", "peripheral", chip_select="cs1", mode=0))
    return d
```
CORPUS entry:
```python
    {"build": _bad_spi_floating_power, "kind": "bad_covered", "expect": {"power-connectivity"},
     "note": "SPI peripheral on no rail"},
```

- [ ] **Step 2: Run — red.** `python3 spike/validator_corpus.py` → exit 1; `bad_spi_floating_power` MISSED (power-connectivity only scans `d.buses`, not SPI yet).

- [ ] **Step 3: Extend the check** — replace `check_power_connectivity` in `seam_validator.py` with (adds the second loop over `d.spi_buses`; the I2C loop is unchanged):

```python
def check_power_connectivity(d: Design) -> list[str]:
    """Every block that participates on a bus (I2C or SPI) must also draw from a power
    rail; an active device on no rail has a floating supply."""
    powered = {block for r in d.rails for (block, _req_v, _tol) in r.sinks}
    errs = []
    for b in d.buses:
        for n in b.nodes:
            if n.block not in powered:
                errs.append(f"POWER: block '{n.block}' on bus '{b.name}' draws from no "
                            f"rail (supply floats)")
    for b in d.spi_buses:
        for n in b.nodes:
            if n.block not in powered:
                errs.append(f"POWER: block '{n.block}' on SPI bus '{b.name}' draws from no "
                            f"rail (supply floats)")
    return errs
```

- [ ] **Step 4: Run — green.** `python3 spike/validator_corpus.py` → exit 0; `bad_spi_floating_power` → `caught [power-connectivity]`. **Also re-confirm `python3 spike/seam_validator.py` exits 0** (the I2C path is untouched).

- [ ] **Step 5: Commit** (`"Extend power-connectivity to SPI bus nodes"`).

### Task 5: publish the SPI false-negative + finalize FN math

**Files:** Modify `spike/validator_corpus.py`

- [ ] **Step 1: Add the published-FN fixture** — add to `validator_corpus.py`:

```python
def _uncov_spi_mode_mismatch() -> sv.Design:
    d = spi_baseline(); d.name = "uncov_spi_mode_mismatch"
    d.rails[1].sinks.append(("flash_b", 3.3, 0.05))
    # mode 3 peripheral vs the mode-0 controller — representable (SPINode.mode) but the
    # gate has no spi-mode-compat check, so it sails through (a measured false negative).
    d.spi_buses[0].nodes.append(sv.SPINode("flash_b", "peripheral", chip_select="cs1", mode=3))
    return d
```
CORPUS entry (note: a `bad_uncovered` entry MUST carry the literal `missing` key — `run()` reads `e['missing']`):
```python
    {"build": _uncov_spi_mode_mismatch, "kind": "bad_uncovered", "missing": "spi-mode-compat",
     "note": "SPI mode-3 peripheral vs mode-0 controller — no spi-mode-compat check yet"},
```

- [ ] **Step 2: Run — confirm the FN math.**

Run: `python3 spike/validator_corpus.py`
Expected: **exit 0**, `RESULT: PASS`. `uncov_spi_mode_mismatch` shows `FALSE NEGATIVE (missing check: spi-mode-compat)` (a published FN, not a regression). The summary now reads:
- `covered faults: 12 detected 12/12`, `uncovered faults: 1 still-missed 1`
- `measured false-negative rate (of all 13 known-bad designs): 1/13 = 8%`
- the "measured false negatives (representable…)" list shows `spi-mode-compat`.

(FN math, explicit: covered 9→12, uncovered 0→1, total_bad = 13, so 1/13 = 8%.)

- [ ] **Step 3: Commit** (`"Publish spi-mode-compat as a measured false negative (FN 0/9 -> 1/13)"`).

### Task 6: block-contract SPI path (schema + build_design + YAML) — CI-verified

**Files:** Modify `spike/block_contract.py`; Create `spike/blocks/mcu_spi_controller.yaml`, `spike/blocks/spi_flash_w25q.yaml`, `spike/slices/spi_node.yaml`

> This task needs `yaml`, so it is **verified in CI** (push the branch; the `spike` job runs `block_contract.py` + `verify_parts.py` + `validator_corpus.py`). Do NOT `pip install` to run it locally.

- [ ] **Step 1: Extend the schema** — in `spike/block_contract.py` `_validate_spec`, the port-type guard currently allows only `("power", "i2c")`. Add `"spi"` and validate it:

```python
        if t not in ("power", "i2c", "spi"):
            raise ValueError(f"{src}: port '{pname}' has unknown type {t!r}")
        if t == "power":
            ...   # unchanged
        elif t == "i2c":
            ...   # the existing i2c branch, unchanged
        else:  # spi
            if p.get("role") not in ("controller", "peripheral"):
                raise ValueError(f"{src}: spi port '{pname}' bad role {p.get('role')!r}")
            if p["role"] == "peripheral" and "chip_select" not in p:
                raise ValueError(f"{src}: spi peripheral '{pname}' missing 'chip_select'")
```
(Refactor the existing `if t == "power": ... else: # i2c ...` into `if/elif/else` so the SPI branch slots in cleanly.)

- [ ] **Step 2: Guard the I2C bus loop + add the SPI loop** — in `build_design`, the existing `for b in slice_doc.get("buses", [])` loop builds an `I2CBus` for *every* bus. Add a type guard so it skips SPI buses, then add a parallel SPI loop:

```python
    buses = []
    for b in slice_doc.get("buses", []):
        if b.get("type") == "spi":
            continue                      # built below
        nodes, pullup = [], None
        ...                               # unchanged I2C body
        buses.append(sv.I2CBus(...))

    spi_buses = []
    for b in slice_doc.get("buses", []):
        if b.get("type") != "spi":
            continue
        nodes = []
        for ref in b.get("members", []):
            inst, sp = resolve(ref)
            nodes.append(sv.SPINode(block=inst, role=sp["role"],
                                    chip_select=sp.get("chip_select"),
                                    mode=sp.get("mode", 0)))
        spi_buses.append(sv.SPIBus(b["name"], nodes=nodes))

    design = sv.Design(slice_doc["name"], rails=rails, buses=buses, spi_buses=spi_buses)
```

- [ ] **Step 3: Create the abstract SPI controller block** — `spike/blocks/mcu_spi_controller.yaml`:

```yaml
id: mcu_spi_controller
version: 0.1.0
function: "SPI controller (abstract; the STM32 binds it in the routed board)"
tags: [controller, mcu, spi]
ports:
  power: {type: power, role: sink, voltage: 3.3, tolerance: 0.05, current_ma: 50}
  spi: {type: spi, role: controller, mode: 0}
```

- [ ] **Step 4: Create the abstract flash block** — `spike/blocks/spi_flash_w25q.yaml`:

```yaml
id: spi_flash_w25q
version: 0.1.0
function: "SPI NOR flash (abstract; bound to W25Q128 / C97521 in the routed-board workstream)"
tags: [memory, flash, spi]
ports:
  power: {type: power, role: sink, voltage: 3.3, tolerance: 0.05, current_ma: 25}
  spi: {type: spi, role: peripheral, chip_select: cs0, mode: 0}
```

- [ ] **Step 5: Create the slice** — `spike/slices/spi_node.yaml`:

```yaml
name: spi_node
instances:
  psu: power_3v3_ldo
  mcu: mcu_spi_controller
  flash: spi_flash_w25q
rails:
  - name: "5V"
    source: {voltage: 5.0, tolerance: 0.05}
    sinks: [psu.power_in]
  - name: "3V3"
    source_from: psu.power_out
    sinks: [mcu.power, flash.power]
buses:
  - name: spi_bus
    type: spi
    members: [mcu.spi, flash.spi]
```

- [ ] **Step 6: Exercise it in the block-contract selftest** — in `block_contract.py` `__main__`, after the existing `sensor_node` validation, also load + validate the SPI slice:

```python
    spi_design = load_slice(HERE / "slices" / "spi_node.yaml", blocks)
    print("\nvalidating authored SPI slice:")
    all_ok &= report(spi_design)
```
(`load_slice`/`report`/`build_design` already exist; this just runs the SPI slice through the same path. The SPI slice is a *good* design, so `report` must show `[PASS] spi_node`.)

- [ ] **Step 7: Push and verify in CI**

```bash
git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/spi-validator-breadth -u
gh run watch --repo benseverndev-oss/NL-Devices <run-id> --exit-status
```
Expected: the `spike` job passes — `block_contract.py` prints `[PASS] spi_node`, `verify_parts.py` treats the two new abstract blocks as UNVERIFIABLE (not a failure), `validator_corpus.py` is green at 1/13. (The `route` job still routes only the untouched `verified` board.)

- [ ] **Step 8: Commit** (before pushing, or amend): `"Add SPI block-contract path: spi port schema + build_design + abstract blocks + slice"`.

### Task 7: PR + merge on green

- [ ] Open the PR (`--base claude/brainstorm-idea-vegk59 --head feat/spi-validator-breadth`), title "Validator learns SPI (FN 0/9 → 1/13)", body summarizing the additive model + checks + published FN.
- [ ] Confirm all 3 CI jobs green (`gh pr checks <n>`), then `gh pr merge <n> --squash --delete-branch`.

---

# Workstream 2 — routed SPI board

**Branch:** `feat/spi-routed-board`, off trunk **after WS1 merges** (`git fetch && git checkout -b feat/spi-routed-board origin/claude/brainstorm-idea-vegk59`).
**Entirely CI-verified** (no local `ato build`/KiCad/freerouting/pip). The proven `verified` board stays byte-for-byte unchanged.

### Task 8: create + commit the real W25Q128 part, ingest the snapshot, bind the flash block

**Files:** Create `spike/atopile/elec/src/parts/Winbond_W25Q128.../**` (in CI); Modify `spike/parts_snapshot.json`, `spike/blocks/spi_flash_w25q.yaml`

> All part creation runs in CI (it needs the atopile toolchain + network). Author a temporary CI workflow step or a one-off job that runs the commands below, commits the artifacts back with `[skip ci]` + `permissions: contents: write`, then `git pull`.

- [ ] **Step 1:** In a CI step, `ato create part -s C97521 -a` (W25Q128JVSIQ), then copy the generated `.ato` / `.kicad_sym` / `.kicad_mod` / `.step` into `spike/atopile/elec/src/parts/Winbond_Elec_W25Q128JVSIQ/` (match the existing part-dir naming), un-ignore the `.step` if needed (per `spike/.gitignore`), and commit them back.
- [ ] **Step 2:** Ingest the part into the ground-truth snapshot: `python3 spike/partdb.py ingest` (EasyEDA fetch for C97521) → updates `spike/parts_snapshot.json`. Commit.
- [ ] **Step 3:** Bind the flash block — edit `spike/blocks/spi_flash_w25q.yaml`, add:

```yaml
bound_part:
  lcsc: C97521
  mpn: W25Q128JVSIQ
  manufacturer: Winbond Elec
  footprint: SOIC-8
```

- [ ] **Step 4:** Push; confirm the `spike` job's `verify_parts.py` now finds C97521 in the snapshot (VERIFIED, not MISSING). Commit if CI committed artifacts back.

### Task 9: `McuSpiBlock` + `SpiFlashBlock` (atopile, standalone)

**Files:** Modify `spike/atopile/verified_lib.ato`

- [ ] **Step 1: Add `McuSpiBlock`** to `verified_lib.ato` (a NEW module — do NOT modify the existing `McuBlock`). Wire the STM32 as an SPI controller: power/decoupling/reset/BOOT0 exactly like `McuBlock`, but expose an SPI interface instead of I2C — `mcu.PA5 ~ spi.sclk`, `mcu.PA6 ~ spi.miso`, `mcu.PA7 ~ spi.mosi`, and a CS signal `mcu.PA4 ~ cs`. (Duplicating the STM32 power/reset boilerplate is intentional isolation — see spec non-goals.)
- [ ] **Step 2: Add `SpiFlashBlock`** to `verified_lib.ato`: instantiate the committed `Winbond_Elec_W25Q128JVSIQ` part; `VCC~power.hv`, `GND~power.lv`, `CLK~spi.sclk`, `DI~spi.mosi`, `DO~spi.miso`, `/CS~cs`, `/WP~power.hv`, `/HOLD~power.hv` (single-SPI, protection off), + a 100nF decoupling cap. Use the real pin names from the generated `.ato` (verify against pin1 /CS, pin2 DO, pin3 /WP, pin4 GND, pin5 DI, pin6 CLK, pin7 /HOLD, pin8 VCC).
- [ ] **Step 3: SPI interface** — use faebryk's `import SPI` (sclk/mosi/miso) if it resolves; CS is a separate `signal`. **Fallback if `ato build` errors on `import SPI`:** declare a minimal `interface SPI: signal sclk; signal mosi; signal miso` in the `.ato` and use that. Decide on the first CI build.

### Task 10: `spi_slice.ato` App + `spi_node` target + route it in CI

**Files:** Create `spike/atopile/spi_slice.ato`; Modify `spike/atopile/ato.yaml`, `.github/workflows/ci.yml`

- [ ] **Step 1: Write `spi_slice.ato`** — a hand-written `App` (mirroring `verified_slice.ato`): `from "verified_lib.ato" import PowerBlock, McuSpiBlock, SpiFlashBlock`; compose `psu`/`mcu`/`flash` on 5V→3V3, wire the SPI bus controller→flash and the CS signal.
- [ ] **Step 2: Add the build target** to `ato.yaml`:

```yaml
  spi_node:
    entry: spi_slice.ato:App
```

- [ ] **Step 3: Add a route step/job** in `ci.yml` mirroring the `verified` route: `ato build -b spi_node`, then `python3 spike/route.py --pipeline --board spike/atopile/elec/layout/spi_node/spi_node.kicad_pcb --jar freerouting.jar --specctra spike/scripts/kicad_specctra.py --work spike/build/route_spi`. Hard-gated on 0 unrouted / 0 DRC. (Add as a second target in the existing `route` job to reuse the toolchain setup.)
- [ ] **Step 4: Push, watch CI.** If `ato build` fails on `import SPI` → apply the Task 9 fallback. If the route misses 0/0 → escalation ladder (freerouting `-mp` ↑ → `SPACING_MM` ↑ → 4-layer only with human sign-off). Iterate until the `spi_node` route job is green.
- [ ] **Step 5: Confirm** the `verified` route job is still green (unchanged) and `fab_export` validates the SPI routed package. Commit.

### Task 11: PR + merge on green

- [ ] Open the PR (`--head feat/spi-routed-board`), title "Route a real STM32 + W25Q128 SPI board (0/0)".
- [ ] All CI jobs green (both `verified` and `spi_node` routes), then `gh pr merge <n> --squash --delete-branch`.

---

## Done when

- `validator_corpus.py` reports **1/13 (8%)** FN with `spi-single-controller` + `spi-chip-select-unique` enforced and `power-connectivity` catching floating SPI nodes; `seam_validator.py` + `block_contract.py --faults` still green; `CHECKS` = 11.
- `block_contract.py` validates the `spi_node` slice `[PASS]`; `verify_parts` green.
- `spi_node` builds and routes at 0/0, 2 layers, fab package valid; the `verified` (I2C) board unaffected.
- Both PRs merged to trunk on green.
