# STM32 board + validator FN checks — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a real STM32F103C8T6 on the `verified` board (routed at the hard 0-unrouted / 0-DRC gate) and close the two known validator false-negatives (`power-connectivity`, `i2c-multimaster`), dropping the measured FN rate 2/9 (22%) → 0/9 (0%).

**Architecture:** Two independent, CI-gated workstreams, sequenced board-first. **A** edits one atopile source file (`verified_slice.ato`) to compose the shared library's real MCU block instead of a chip-less stub, and is verified only by the CI `route` job. **B** adds two pure-Python checks to `seam_validator.py` and reclassifies the two matching adversarial-corpus entries, verified by `validator_corpus.py`.

**Tech Stack:** atopile 0.12.5 (`.ato`), KiCad 9 + freerouting 2.1.0 (CI only), Python 3.13 stdlib (validator).

---

## ⚠️ Execution constraints (read first)

- **NEVER run heavy compute locally — it OOMs the owner's box.** Do **not** run `ato build`, `pip install`, KiCad, or freerouting on this machine. The CI GitHub runners are the test runner for Workstream A. Author files locally, push, watch CI.
- **Workstream B is safe to run locally.** `seam_validator.py` and `validator_corpus.py` import only the Python stdlib (`dataclasses`, `sys`). Run them directly — **do not** `pip install -r spike/requirements.txt` (that's the OOM trigger and is unneeded here).
- **Push over the embedded-token URL** (gh as `benzsevern`):
  `git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git <branch>`
- **Cadence:** branch off trunk `claude/brainstorm-idea-vegk59` → CI green → `gh pr merge <n> --squash --delete-branch`.
- **Verify merge state by fetching + comparing trees, never `git merge-base --is-ancestor <pre-squash-sha>`** (squash-merges make that always false).

---

## File Structure

| File | Workstream | Responsibility | Action |
|------|-----------|----------------|--------|
| `spike/atopile/verified_slice.ato` | A | Top `App` for the `verified` build target | **Modify** — import the real blocks from `verified_lib.ato`, strap EEPROM address pins |
| `spike/atopile/verified_lib.ato` | A | Shared block library (source of truth) | Read-only (fallback A′ may trim it) |
| `spike/seam_validator.py` | B | The seam-validation gate (`CHECKS`) | **Modify** — add 2 check functions + register |
| `spike/validator_corpus.py` | B | Adversarial FN-measurement corpus | **Modify** — reclassify 2 entries, power 3 fixtures |
| `docs/superpowers/plans/2026-06-09-stm32-board-and-validator-fn-checks.md` | — | This plan | Commit on the Workstream-A branch |

---

# Workstream A — real STM32 on the `verified` board

**Branch:** `feat/stm32-verified-board` (already exists; carries the spec + this plan).
**Verified by:** the CI `route` job (`ato build -b verified` → place → freerouting → DRC → Gerbers → fab package), hard-gated on 0 unrouted + 0 DRC.

### Task A1: Compose the real MCU block + strap the EEPROM address

**Files:**
- Modify: `spike/atopile/verified_slice.ato` (full rewrite of the file)

- [ ] **Step 1: Commit this plan + the spec to the branch** (if not already pushed)

```bash
git checkout feat/stm32-verified-board
git add docs/superpowers/plans/2026-06-09-stm32-board-and-validator-fn-checks.md
git commit -m "Plan: STM32 verified board + validator FN checks"
```

- [ ] **Step 2: Rewrite `verified_slice.ato`** to import the shared blocks and strap the EEPROM address pins. Replace the entire file with:

```ato
# The `verified` build target's top App. Composes the THREE real verified blocks
# (LDO + STM32 MCU + EEPROM) from the shared library `verified_lib.ato` — the same
# blocks the orchestrator's codegen emits — so the routed board and the composed board
# share ONE definition. (This file previously re-defined its own chip-less MCU stub;
# that stub is gone — the board now has a real brain.)

import ElectricPower
import I2C

from "verified_lib.ato" import PowerBlock, McuBlock, EepromBlock

module App:
    power5v = new ElectricPower
    power3v3 = new ElectricPower
    assert power5v.voltage within 5V +/- 5%

    psu = new PowerBlock
    mcu = new McuBlock
    sensor = new EepromBlock

    psu.power_in ~ power5v
    psu.power_out ~ power3v3
    mcu.power ~ power3v3
    sensor.power ~ power3v3

    # EEPROM address straps: A0/A1/A2 low -> I2C address 0x50.
    # (EepromBlock straps WP internally but leaves A0/A1/A2 to the parent, exactly as
    # codegen does in the orchestrator path.)
    sensor.eeprom.A0 ~ power3v3.lv
    sensor.eeprom.A1 ~ power3v3.lv
    sensor.eeprom.A2 ~ power3v3.lv

    i2c_bus = new I2C
    i2c_bus.frequency = 400kHz
    mcu.i2c ~ i2c_bus
    sensor.i2c ~ i2c_bus
```

- [ ] **Step 3: Sanity-check locally WITHOUT building.** Confirm the file no longer defines the stub blocks and the imports are present. (Do NOT run `ato build`.)

Run: `grep -nE "from \"verified_lib.ato\"|module App|sensor.eeprom.A|module McuBlock" spike/atopile/verified_slice.ato`
Expected: the import line + `module App` + the three `sensor.eeprom.A*` straps appear; **`module McuBlock` does NOT appear** (the stub is gone).

- [ ] **Step 4: Commit**

```bash
git add spike/atopile/verified_slice.ato
git commit -m "Put the real STM32F103C8T6 on the verified board

Swap the chip-less stub McuBlock in verified_slice.ato:App for the real
STM32 block from the shared verified_lib.ato (dedup to one definition).
Strap the EEPROM A0/A1/A2 low for 0x50 (the imported EepromBlock leaves
them to the parent). The verified board now actually computes."
```

- [ ] **Step 5: Push and watch the CI `route` job** (this is the test)

```bash
git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/stm32-verified-board -u
gh run watch --repo benseverndev-oss/NL-Devices $(gh run list --repo benseverndev-oss/NL-Devices --branch feat/stm32-verified-board --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected (success): the `Autoroute → routed copper (verified board)` job passes — `route.py --pipeline` reports `unrouted=0`, `DRC violations=0`, all `REQUIRED_LAYERS` present, fab package valid.

**If the job fails, go to the matching contingency task below, then return here and re-push.**

### Task A2 (contingency): `ato build` fails on the cross-file import (Approach A′ — inline)

Trigger: the `ato build verified` step errors on `from "verified_lib.ato" import ...` or on `parts/…` resolution.

- [ ] **Step 1: Inline the real `McuBlock`** into `verified_slice.ato` instead of importing it. Copy the full `McuBlock` module body (the STM32 version) verbatim from `spike/atopile/verified_lib.ato`, plus its `from "parts/STMicroelectronics_STM32F103C8T6/…" import …​` line and the `Capacitor`/`Resistor` imports it needs. Do the same for `PowerBlock` and `EepromBlock` (or import only the ones that resolve). Keep `App` identical (including the `sensor.eeprom.A*` straps).
- [ ] **Step 2:** Remove the now-redundant duplicate block defs from `verified_lib.ato` **only if** doing so doesn't break `codegen.py` (grep `codegen.py` for the block names first; if codegen imports them, leave `verified_lib.ato` as the source and instead keep the inline copy minimal). Goal: one authoritative definition, no silent divergence.
- [ ] **Step 3:** Commit (`"A′ fallback: inline the STM32 blocks (cross-file import unsupported)"`), push, re-watch CI per A1 Step 5.

### Task A3 (contingency): routing does not converge to 0 unrouted / 0 DRC

Trigger: the `route` job reports `unrouted > 0` or DRC violations. Apply the **escalation ladder smallest-change-first**, re-pushing and re-watching CI after each rung; stop as soon as it's 0/0.

- [ ] **Rung 1 — more freerouting effort.** In `spike/route.py`, raise the freerouting `-mp` pass count above 100 (e.g. 200) in `run_freerouting`. Commit, push, watch.
- [ ] **Rung 2 — open routing channels.** In `spike/place.py`, raise `SPACING_MM` (e.g. 2.0 → 3.0) so courtyards spread and freerouting has more room. Commit, push, watch.
- [ ] **Rung 3 — LAST RESORT, 4-layer.** Only if 2-layer is proven not to converge. Changes are larger: add `In1.Cu`/`In2.Cu` to `route.py:REQUIRED_LAYERS` and to `export_gerbers`, and give the board a 4-layer stackup in the Specctra/DRC path. Treat as its own mini-spec; surface to the human before doing it.

### Task A4: Open the PR and merge on green

- [ ] **Step 1:** `gh pr create --repo benseverndev-oss/NL-Devices --base claude/brainstorm-idea-vegk59 --head feat/stm32-verified-board --title "Put the real STM32 on the verified board" --body "<summary: real MCU board routes at 0/0; dedup to shared block lib; EEPROM straps. Spec: docs/superpowers/specs/2026-06-09-…">"`
- [ ] **Step 2:** Confirm all three CI jobs green (`gh pr checks <n>`).
- [ ] **Step 3:** `gh pr merge <n> --squash --delete-branch`.

---

# Workstream B — validator false-negative checks

**Branch:** `feat/validator-fn-checks`, off trunk **after Workstream A merges** (so trunk carries the spec/plan; the two are independent, so parallel off trunk is also acceptable).
**Verified by:** `python3 spike/validator_corpus.py` (stdlib-only, runs locally and in the CI `spike` job).

```bash
git fetch origin
git checkout -b feat/validator-fn-checks origin/claude/brainstorm-idea-vegk59
```

> Run all `python3 spike/*.py` commands from the **repo root**; Python puts the script's own dir (`spike/`) on `sys.path`, so `import seam_validator` resolves. **No `pip install`.**

### Task B1: `power-connectivity` check

**Files:**
- Modify: `spike/seam_validator.py` (add function + register in `CHECKS`)
- Modify: `spike/validator_corpus.py` (reclassify `_uncov_floating_power`; power `sensor_b` in `_bad_addr_collision`)

- [ ] **Step 1: Write the failing test** — in `spike/validator_corpus.py`, reclassify the floating-power entry to a covered regression guard. Rename the builder for honesty and change its CORPUS entry.

Rename `_uncov_floating_power` → `_bad_floating_power` (and its `d.name = "bad_floating_power"`). Leave the `orphan` node off every rail (that IS the fault). In `CORPUS`, replace its entry with:

```python
    {"build": _bad_floating_power, "kind": "bad_covered", "expect": {"power-connectivity"},
     "note": "active device on no rail — power-connectivity must fire"},
```

- [ ] **Step 2: Run the corpus to verify it fails**

Run: `python3 spike/validator_corpus.py`
Expected: **FAIL** (exit 1), because the check doesn't exist yet. The `bad_floating_power` row shows `MISSED expected ['power-connectivity'], got ∅`; the regressions list at the bottom shows `MISSED: bad 'bad_floating_power' expected ['power-connectivity'], got []` (note: the row renders `∅`, the regressions line renders `[]` — same thing); `RESULT: FAIL`.

- [ ] **Step 3: Implement `check_power_connectivity`** — in `spike/seam_validator.py`, add this after `check_part_rail_rating` (before the `CHECKS` list):

```python
def check_power_connectivity(d: Design) -> list[str]:
    """Every block that participates on a bus must also draw from a power rail; an
    active device on no rail has a floating supply. A structural false-negative the
    other checks miss (they only reason about blocks already on a rail/bus)."""
    powered = {block for r in d.rails for (block, _req_v, _tol) in r.sinks}
    errs = []
    for b in d.buses:
        for n in b.nodes:
            if n.block not in powered:
                errs.append(f"POWER: block '{n.block}' on bus '{b.name}' draws from no "
                            f"rail (supply floats)")
    return errs
```

- [ ] **Step 4: Register it** — append to the `CHECKS` list:

```python
          ("power-connectivity", check_power_connectivity),
```

- [ ] **Step 5: Power the clean-up fixture** — in `spike/validator_corpus.py`, `_bad_addr_collision` adds `sensor_b` to the bus but no rail, so the new check would co-fire. Add `sensor_b` to the 3V3 rail so the case stays single-fault. Edit `_bad_addr_collision`:

```python
def _bad_addr_collision() -> sv.Design:
    d = good_baseline(); d.name = "bad_addr_collision"
    d.rails[1].sinks.append(("sensor_b", 3.3, 0.05))   # power it: keep this a single-fault case
    d.buses[0].nodes.append(sv.I2CNode("sensor_b", "peripheral", address=0x50))
    return d
```

- [ ] **Step 6: Run the corpus to verify it passes**

Run: `python3 spike/validator_corpus.py`
Expected: **PASS** (exit 0). `bad_floating_power` shows `caught [power-connectivity]`; `bad_addr_collision` still shows `caught [i2c-address]` only; 0 false positives; `RESULT: PASS`. (Note: at this point `power-connectivity` also fires on the still-unpowered `mcu2` in the multimaster fixture, so the `uncov_multimaster` row shows `now caught [power-connectivity] — reclassify as covered` — a non-regressing "surprise", not a failure — and the FN rate already reads 0/9. B2 converts that fixture into a clean single-fault `i2c-multimaster` guard.)

- [ ] **Step 7: Commit**

```bash
git add spike/seam_validator.py spike/validator_corpus.py
git commit -m "Add power-connectivity check; close the floating-power false negative

Every block on a bus must draw from a rail. Reclassify the floating-power
corpus entry to bad_covered (regression guard) and power sensor_b so the
address-collision case stays single-fault."
```

### Task B2: `i2c-multimaster` check

**Files:**
- Modify: `spike/seam_validator.py` (add function + register)
- Modify: `spike/validator_corpus.py` (reclassify `_uncov_multimaster`; power `mcu2`)

- [ ] **Step 1: Write the failing test** — in `spike/validator_corpus.py`, rename `_uncov_multimaster` → `_bad_multimaster` (and `d.name = "bad_multimaster"`), power `mcu2` so only the multimaster check fires, and reclassify the CORPUS entry.

```python
def _bad_multimaster() -> sv.Design:
    d = good_baseline(); d.name = "bad_multimaster"
    d.rails[1].sinks.append(("mcu2", 3.3, 0.05))   # power it: isolate the multimaster fault
    d.buses[0].nodes.append(sv.I2CNode("mcu2", "controller", provides_pullups=False))
    return d
```

CORPUS entry becomes:

```python
    {"build": _bad_multimaster, "kind": "bad_covered", "expect": {"i2c-multimaster"},
     "note": "two controllers on one bus — i2c-multimaster must fire"},
```

- [ ] **Step 2: Run the corpus to verify it fails**

Run: `python3 spike/validator_corpus.py`
Expected: **FAIL** (exit 1). `mcu2` is now powered, so `power-connectivity` does not fire — the case is clean-red on the missing multimaster check only: the `bad_multimaster` row shows `MISSED expected ['i2c-multimaster'], got ∅` (regressions line: `got []`), `RESULT: FAIL`.

- [ ] **Step 3: Implement `check_i2c_multimaster`** — in `spike/seam_validator.py`, add after `check_power_connectivity`:

```python
def check_i2c_multimaster(d: Design) -> list[str]:
    """At most one controller (bus master) per I2C bus. Two masters sharing SCL/SDA is
    an arbitration / clock-ownership hazard the single-controller topology here does
    not support."""
    errs = []
    for b in d.buses:
        controllers = [n.block for n in b.nodes if n.role == 'controller']
        if len(controllers) > 1:
            errs.append(f"I2C: bus '{b.name}' has {len(controllers)} controllers "
                        f"({', '.join(controllers)}); multi-master not supported")
    return errs
```

- [ ] **Step 4: Register it** — append to `CHECKS`:

```python
          ("i2c-multimaster", check_i2c_multimaster),
```

- [ ] **Step 5: Run the corpus to verify it passes + FN rate is 0**

Run: `python3 spike/validator_corpus.py`
Expected: **PASS** (exit 0). `bad_multimaster` shows `caught [i2c-multimaster]`; the summary line reads `measured false-negative rate (of all 9 known-bad designs): 0/9 = 0%`; the "measured false negatives (representable…)" list is now empty; `NOT_MODELLED` unchanged; `RESULT: PASS`.

- [ ] **Step 6: Confirm `seam_validator.py`'s own selftest still passes**

Run: `python3 spike/seam_validator.py`
Expected: **PASS** (exit 0) — its `__main__` verdict reads only the original 3 columns, so the 2 new checks don't perturb it.

- [ ] **Step 7: Commit**

```bash
git add spike/seam_validator.py spike/validator_corpus.py
git commit -m "Add i2c-multimaster check; FN rate now 0/9

Flag >1 controller on a bus. Reclassify the multimaster corpus entry to
bad_covered and power mcu2 so it's single-fault. Representable false-negative
inventory is now empty."
```

### Task B3: PR and merge on green

- [ ] **Step 1:** Push: `git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/validator-fn-checks -u`
- [ ] **Step 2:** `gh pr create --repo benseverndev-oss/NL-Devices --base claude/brainstorm-idea-vegk59 --head feat/validator-fn-checks --title "Validator: power-connectivity + i2c-multimaster (FN rate 2/9 → 0/9)" --body "<summary + spec link>"`
- [ ] **Step 3:** Confirm the `spike` job (which runs `validator_corpus.py`) is green, then `gh pr merge <n> --squash --delete-branch`.

---

## Done when

- The `verified` board routes in CI with a real STM32F103C8T6 (LQFP-48) + AMS1117-3.3 + AT24C256 at 0 unrouted / 0 DRC, on 2 layers, fab package valid.
- `verified_slice.ato` and `verified_lib.ato` share one block definition.
- `validator_corpus.py` reports 0/9 (0%) measured FN rate with `power-connectivity` and `i2c-multimaster` enforced as regression guards; `seam_validator.py` selftest still green.
- Both PRs merged to trunk on green.
