# Design: SPI breadth — teach the validator a second bus, then route a real SPI board

**Date:** 2026-06-09
**Status:** Approved (design); implementation pending
**Trunk:** `claude/brainstorm-idea-vegk59` (tip `adb0033`)

## Summary

The seam-validator has only ever seen one bus shape (I2C) and one topology (I2C + LDO):
4 of its 9 checks are `i2c-*`, the `Design` model's only bus type is `I2CBus`, and
`block_contract.build_design` only builds I2C buses. This work stresses that by adding
**SPI** — a bus with fundamentally different rules (per-peripheral chip-select, shared
SCLK/MOSI/MISO, no addressing) — across the full vertical: first the validator learns
SPI and we measure/close the new false-negatives it surfaces, then we build and route a
real STM32 + SPI-flash board to fab-ready copper.

Two independent, CI-gated workstreams, sequenced validator-first:

1. **Validator learns SPI** (pure stdlib Python + YAML, `spike` job). Additive `SPIBus`
   model + two new SPI checks + an extension to `power-connectivity`, proven with
   adversarial corpus cases. Surfaces one *new* honest false-negative (`spi-mode-compat`)
   we publish rather than close — keeping the measured-FN methodology intact.
2. **Routed SPI board** (atopile + route, new CI target). A real Winbond W25Q128 SPI NOR
   flash + an STM32-as-SPI-controller block, composed into a new `spi_node` build target
   and routed at the hard 0-unrouted / 0-DRC gate.

## Goals

- The validator's `Design` model, block schema, and `build_design` represent SPI buses,
  and `CHECKS` gains `spi-single-controller` + `spi-chip-select-unique`, with
  `power-connectivity` extended to SPI nodes.
- The adversarial corpus measures SPI coverage: the new structural SPI faults are caught
  (regression guards), and the one representable SPI fault we *don't* yet check
  (`spi-mode-compat`) is published as a measured false-negative — FN rate moves from
  0/9 to **1/13** (honest: breadth added coverage *and* surfaced a new gap).
- A `spi_node` atopile target builds and **routes** an STM32 (SPI controller) + W25Q128
  (SPI peripheral) board at **0 unrouted / 0 DRC**, 2 layers, fab package valid.

## Non-goals (YAGNI)

- Generic `Bus` refactor (keep `I2CBus` + `SPIBus` parallel; wait for a third bus).
- NL/orchestrator composing SPI designs (the `spi_node` App is hand-written, not planned).
- Extracting a shared STM32 core between `McuBlock` and `McuSpiBlock` (accept boilerplate
  duplication to protect the proven I2C verified-board route; refactor at rule-of-three).
- Implementing `spi-mode-compat` now (ship it as a published FN; closing it is the next
  obvious follow-up the corpus will point at).
- QSPI / multi-CS daisy-chaining / SPI flash filesystem.

---

## Workstream 1 — validator learns SPI

Pure additive change; the proven I2C path is untouched. SPI's CS is point-to-point
(per peripheral), so it is modelled per-node, not as a shared bus line.

### Schema (`block_contract._validate_spec`)

Accept a third port `type: "spi"`:
- `role` ∈ `{controller, peripheral}` (required).
- a peripheral requires `chip_select` (a CS net id, string); a controller has none.
- optional `mode` (0..3, default 0).

### Design model (`seam_validator.py`)

Add, alongside `I2CNode`/`I2CBus`:
```python
@dataclass
class SPINode:
    block: str
    role: str                       # 'controller' | 'peripheral'
    chip_select: str | None = None  # CS net id (peripherals only)
    mode: int = 0                   # SPI mode 0..3 — modelled, NOT yet checked

@dataclass
class SPIBus:
    name: str
    nodes: list[SPINode] = field(default_factory=list)
    speed_hz: int = 1_000_000
```
and `spi_buses: list[SPIBus] = field(default_factory=list)` to `Design`. (`I2CBus` and
`Design.buses` are unchanged.)

### `build_design` (`block_contract.py`)

Add a loop mirroring the I2C one: for each slice bus with `type: spi`, build an `SPIBus`
of `SPINode`s from its `members` (each member ref resolves to its block's `spi` port spec
→ `role` / `chip_select` / `mode`). I2C buses (`type: i2c` or untyped) continue to build
`I2CBus` exactly as today.

### Checks (registered in `CHECKS`)

- **`spi-single-controller`** — each SPI bus must have exactly one controller; flag
  `len(controllers) != 1` (0 = no master, ≥2 = contention).
- **`spi-chip-select-unique`** — no two peripherals on a bus share a `chip_select`; also
  flag a peripheral with no `chip_select`.
- **Extend `check_power_connectivity`** — after scanning `d.buses` (I2C), also scan
  `d.spi_buses`: every SPI node's block must be a rail sink, else its supply floats.
  (Without this, a floating SPI peripheral is a silent FN — the coupling the stress
  exposes.)

`spi-mode-compat` (a peripheral whose `mode` differs from the controller's) is **not**
implemented; `SPINode.mode` makes it representable so the corpus can publish it as a
measured FN.

### Slice + block YAML

- `spike/blocks/spi_flash_w25q.yaml` — **abstract** for WS1 (no `bound_part`, so
  `verify_parts` treats it UNVERIFIABLE, not a failure): a `power` sink + an `spi`
  peripheral port (`chip_select`, `mode: 0`). WS2 binds it to the real part.
- `spike/slices/spi_node.yaml` — composes an MCU-as-SPI-controller block + the flash over
  a `type: spi` bus, on the 3V3 rail.

### Corpus (`validator_corpus.py`)

Add SPI fixtures (mutating a fresh SPI baseline):
- `good_spi_node` (good): one controller + one peripheral, distinct CS, mode-matched,
  both powered → clean.
- `bad_spi_cs_collision` (`bad_covered`, `spi-chip-select-unique`): two peripherals share
  CS.
- `bad_spi_no_controller` (`bad_covered`, `spi-single-controller`): a bus of peripherals,
  no master.
- `bad_spi_floating_power` (`bad_covered`, `power-connectivity`): an SPI peripheral on no
  rail.
- `uncov_spi_mode_mismatch` (`bad_uncovered`, missing `spi-mode-compat`): a peripheral at
  mode 3 vs a mode-0 controller — the published SPI false-negative.

### WS1 success criteria

- `python3 spike/validator_corpus.py` exits 0: existing 9 known-bad still 9/9 covered,
  the 3 new SPI faults caught, 0 false positives, and the summary reports **1/13 (8%)**
  measured FN rate with `spi-mode-compat` as the single published representable FN.
- `python3 spike/seam_validator.py` and `python3 spike/block_contract.py --faults` still
  exit 0 (the I2C selftests are unaffected; SPI is additive).
- `CHECKS` is now 11 entries.

---

## Workstream 2 — routed SPI board

### Real part

- **Winbond W25Q128JVSIQ** SPI NOR flash, **LCSC C97521**, SOIC-8 (208mil). Standard
  4-wire SPI: pin1 /CS, pin2 DO(MISO), pin3 /WP, pin4 GND, pin5 DI(MOSI), pin6 CLK,
  pin7 /HOLD, pin8 VCC.
- `ato create part -s C97521 -a` in CI → commit `.ato` / `.kicad_sym` / `.kicad_mod` /
  `.step` under `elec/src/parts/**` (the STM32 pattern, decision 0005).
- Ingest into `parts_snapshot.json` (`partdb.py ingest`, EasyEDA fetch) so `verify_parts`
  passes once the flash block is bound. WS2 also flips `spi_flash_w25q.yaml` from abstract
  to bound (`lcsc: C97521`).

### Blocks (`verified_lib.ato`)

- **`McuSpiBlock`** — STM32F103C8T6 wired as an SPI controller: SPI1 on PA5 (SCK), PA6
  (MISO), PA7 (MOSI), PA4 as the CS GPIO; plus its own full power (every VDD/VSS),
  decoupling (3×100nF + 4.7µF + 1µF), reset RC, and BOOT0 pulldown. **Standalone** —
  does not touch the proven I2C `McuBlock` or the `verified` board.
- **`SpiFlashBlock`** — W25Q128: VCC/GND to the rail, CLK/DI/DO to the SPI bus, /CS to the
  controller's CS, /WP and /HOLD tied high (single-SPI, protection off), plus a 100nF
  decoupling cap.

### Composition + target

- New build target `spi_node` (`ato.yaml`) → `spi_slice.ato:App`, a **hand-written** App
  composing `psu` (existing `PowerBlock`) + `mcu` (`McuSpiBlock`) + `flash`
  (`SpiFlashBlock`) on a 5V→3V3 supply, with the SPI bus + CS wired controller→flash.
- **SPI typed interface:** assume faebryk's `import SPI` (sclk/mosi/miso) is available in
  atopile 0.12.5; CS is a separate point-to-point signal. **CI-verified assumption** —
  fallback is a minimal custom SPI interface bundle declared in `.ato`.

### CI + routing

- A new `route`-style job (or a second target in the existing `route` job) builds
  `-b spi_node` and runs `spike/route.py --pipeline` against its board, hard-gated on
  **0 unrouted / 0 DRC** + all `REQUIRED_LAYERS`, 2 layers. Same escalation ladder as the
  STM32 board if the first route misses (freerouting passes → `SPACING_MM` → 4-layer last
  resort).
- `fab_export` routed-package build + validation for the SPI board.

### WS2 success criteria

- `ato build -b spi_node` produces a board with the STM32 + W25Q128 over SPI; it routes
  at 0/0 on 2 layers; fab package valid.
- `verify_parts` passes with the now-bound W25Q128 in the snapshot.
- The proven `verified` (I2C) board is byte-for-byte unaffected (separate blocks/target).

---

## Testing & CI

- **`spike` job** (WS1): `validator_corpus.py` enforces the new SPI checks + publishes the
  SPI FN; `seam_validator.py` / `block_contract.py --faults` / `verify_parts.py` stay
  green. No new dependencies.
- **`route` (WS2):** new `spi_node` build + route at the hard gate; existing `verified`
  route untouched.

## Sequencing

WS1 first (the stated goal; pure-Python/YAML; zero part/atopile/network deps because the
flash block is abstract). WS2 second (real part + routed board). Each is its own branch
off trunk → CI green → squash-merge.

## Risks

- **faebryk SPI availability** (WS2) — mitigated by the custom-interface fallback;
  resolved on the first CI `ato build`.
- **W25Q128 routing convergence** (WS2) — STM32 + flash is a small 2-layer board;
  escalation ladder covers it.
- **Snapshot ingest** (WS2) needs an EasyEDA fetch — reachable from the sandbox; if it
  fails, the flash block can stay abstract for WS1's already-merged validator work while
  the part is sourced.
- **CI time** — WS2 adds a second freerouting pass (~1–2 min). Acceptable.

## Rollout

Two branches/PRs off trunk, merged on green, per the repo cadence.
