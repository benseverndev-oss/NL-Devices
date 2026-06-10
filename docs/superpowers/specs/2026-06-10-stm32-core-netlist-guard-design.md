# Design: shared STM32 core, under a netlist-equivalence guard

**Date:** 2026-06-10
**Status:** Approved (design); implementation pending
**Trunk:** `claude/brainstorm-idea-vegk59` (tip `942af5e`)

## Summary

`McuBlock` (I2C, in `verified_lib.ato`, on the `verified` board) and `McuSpiBlock`
(SPI, on the `spi_node` board) duplicate ~48 lines of STM32F103C8T6 boilerplate — every
VDD/VBAT/VDDA→hv & VSS/VSSA→lv tie, the five decoupling caps (3×100nF + 4.7µF bulk +
1µF VDDA), the NRST reset RC, the BOOT0 pulldown, the 3V3 `assert`. They differ only in
the bus tail (I2C on PB6/PB7 + pull-ups vs SPI on PA5/6/7 + PA4 CS).

This extracts the shared part into one `Stm32CoreBlock` that both wrappers compose. The
hard requirement is that it be a **pure refactor**: the emitted netlist for *both*
boards must be electrically unchanged so they keep routing 0/0 (the `verified` route is
marginal — it needed freerouting `-mp 200` + `SPACING_MM 3.0` to converge — so a silent
connectivity change is the real risk). The route gate proves *routability*, not netlist
equivalence, so this work first builds a **netlist-equivalence guard** that proves the
copper matches the design, then does the refactor under it.

Two CI-gated workstreams, **guard-first**:

1. **Netlist-equivalence guard** — a pure-Python `netlist.py` that reduces a built
   `.kicad_pcb` to a canonical, name/refdes-independent connectivity form; golden
   captures for `verified` + `spi_node`; a route-job assertion that every build matches
   its golden. A reusable "the board matches intent" check (validator-depth), not just
   refactor scaffolding.
2. **The refactor** — `Stm32CoreBlock` + two thin wrappers. Under the guard, CI proves
   the boards' connectivity is byte-equivalent; routing 0/0 confirms manufacturability.

## Goals

- One definition of the STM32 power/decoupling/reset/boot core, composed by both
  `McuBlock` and `McuSpiBlock`. No duplicated boilerplate.
- A `netlist.py` that emits a canonical connectivity form and a `--check` mode that
  fails CI on any connectivity change; goldens committed for both boards; the route job
  asserts equivalence on every build.
- Both boards still route at 0 unrouted / 0 DRC, and their netlists match golden
  (proving the refactor changed nothing electrically).

## Non-goals (YAGNI)

- Changing either board's *electrical* design (this is a pure refactor + a guard).
- A full graph-isomorphism netlist comparator — the canonical multiset form (below) is
  sufficient for a mechanical refactor and far simpler.
- Extracting cores for non-STM32 blocks, or parameterizing the core (single fixed MCU).
- Diffing net *names* or reference designators (intentionally ignored — they shift
  cosmetically under nesting without changing connectivity).

---

## Workstream 1 — the netlist-equivalence guard

### `spike/netlist.py` (new, pure stdlib, offline-testable)

Parses a built `.kicad_pcb` (the artifact `ato build` already produces; reuse the
s-expression footprint-block iteration from `place.py`) and reduces it to a **canonical
connectivity form**:

- For each footprint block, read its footprint library id (the `(footprint "lib:name"`
  token), its `(property "Value" "...")`, its `(property "Reference" "...")`, and each
  `(pad "<name>" … (net <id> "<netname>"))`.
- Build nets: map each net id → the multiset of `(footprint_libid, value, pad_name)` of
  the pads on it. **Net 0 (`""`, the unconnected pads) is included** — an intentionally
  floating pin (e.g. SWD PA13/PA14, spare GPIO) must stay floating after the refactor.
- **Canonical form** = `sorted( [ sorted(tuple of (libid, value, pad)) for each net ] )`
  — i.e. each net is its sorted member list, and the whole netlist is the sorted list of
  those, **with net names and reference designators dropped**. Also emit a `parts`
  multiset = sorted `(libid, value)` over all footprints. Serialize to deterministic
  JSON (`sort_keys`, stable separators).

Rationale: a mechanical "move lines into a sub-module" refactor preserves parts and
pad-to-pad connectivity exactly; it only changes the *hierarchy*, which atopile reflects
in net names and refdes — both of which the canonical form ignores. A dropped cap, a
mis-wired pin, or a pin that floats when it shouldn't all change the canonical form and
are caught.

**Modes:**
- `--emit <board.kicad_pcb>` → write the canonical JSON to stdout (used to capture golden).
- `--check <board.kicad_pcb> <golden.json>` → exit 0 if the build's canonical form equals
  golden, else exit 1 printing a readable diff (which nets/parts differ).
- `--selftest` → offline: parse the committed fixture
  (`spike/fixtures/verified/verified.kicad_pcb`), emit, re-parse the emitted form, assert
  determinism (emit is stable across two runs) + basic sanity (≥1 net, every pad
  resolves to a declared net). Run in the `spike` CI job, no toolchain needed.

### Golden capture (CI, committed)

A one-shot CI step (mirror the part-create `[skip ci]` commit-back pattern): build
`verified` + `spi_node`, run `netlist.py --emit` on each, and commit
`spike/fixtures/golden/verified.netlist.json` + `spi_node.netlist.json`. These are the
frozen "intended connectivity" of each board *as it is today* (pre-refactor).

### Route-job integration

In the `route` job, after each board's `ato build` (before or alongside the existing
route gate), run `python3 spike/netlist.py --check
spike/atopile/elec/layout/<board>/<board>.kicad_pcb spike/fixtures/golden/<board>.netlist.json`.
A mismatch fails the job. On trunk today (unchanged boards) this passes trivially, which
proves the guard runs and the golden was captured correctly.

### WS1 success criteria

- `python3 spike/netlist.py --selftest` passes in the `spike` job (offline).
- Goldens for both boards committed under `spike/fixtures/golden/`.
- The `route` job runs `--check` for both boards and they PASS (build == golden), with
  the existing 0/0 route gate unchanged.

---

## Workstream 2 — extract `Stm32CoreBlock`

### The change (`spike/atopile/verified_lib.ato`, additive then internal)

- Add `Stm32CoreBlock`: `power = new ElectricPower`, `mcu = new
  STMicroelectronics_STM32F103C8T6_package`, all the VDD/VBAT/VDDA→`power.hv` &
  VSS/VSSA→`power.lv` ties, the five decoupling caps (dec1–dec3 100nF, bulk 4.7µF, deca
  1µF), the NRST RC (`nrst_pullup` 10k + `nrst_cap` 100nF), the BOOT0 pulldown 10k, and
  `assert power.voltage within 3.3V +/- 5%`. Exposes `power` and `mcu`.
- Rewrite `McuBlock`: `core = new Stm32CoreBlock`; `power ~ core.power`; keep the I2C
  interface + pull-ups, wiring `core.mcu.PB6 ~ i2c.scl.line` / `core.mcu.PB7 ~
  i2c.sda.line`.
- Rewrite `McuSpiBlock`: `core = new Stm32CoreBlock`; `power ~ core.power`; keep the SPI
  interface + `signal cs`, wiring `core.mcu.PA5/PA6/PA7` and `core.mcu.PA4 ~ cs`.
- `PowerBlock` / `EepromBlock` / `SpiFlashBlock` / `TempBlock` and the `verified_slice` /
  `spi_slice` Apps and the build targets are untouched — `McuBlock`/`McuSpiBlock` keep the
  same public interface (`power`, `i2c`/`spi`, `cs`), so the Apps compose them
  identically.

### WS2 success criteria

- `verified_lib.ato` has one `Stm32CoreBlock`; `McuBlock`/`McuSpiBlock` no longer
  duplicate the core boilerplate.
- The `route` job's `netlist.py --check` passes for **both** boards (connectivity ==
  golden) — the refactor is proven electrically inert.
- Both boards still route 0 unrouted / 0 DRC; `verify_parts`/`validator_corpus` green.

---

## Testing & CI

- **`spike` job:** add `python3 spike/netlist.py --selftest` (offline). No new deps.
- **`route` job:** add a `netlist.py --check` step per board after `ato build`; keep the
  0/0 route gate. WS1 adds the golden + check; WS2 is validated by them.
- Golden capture is a one-shot `[skip ci]` CI commit-back (then the temp step is removed).

## Sequencing

WS1 (guard) first — it must exist and pass on the *unchanged* boards before the refactor,
so WS2's pass is meaningful. Each workstream is its own branch off trunk → CI green →
squash-merge. WS2 branches off the post-WS1 trunk.

## Risks

- **Canonical-form instability** — if `ato build` emits a different `Value` string or
  footprint id for the same part across builds, `--check` would false-fail. Mitigated by
  capturing golden from the same toolchain CI uses; if it proves flaky, key on footprint
  libid + LCSC rather than the display `Value`.
- **Hierarchy-induced net changes** — nesting the caps under `core.` changes net names /
  refdes; the canonical form ignores both, so this is expected and harmless. If atopile
  *also* changes connectivity (it shouldn't), `--check` catches it — that's the point.
- **`core.mcu.<pin>` access** — relies on atopile exposing a child module's sub-instance
  pins to the parent (already used: `sensor.eeprom.A0`). If it doesn't resolve, the build
  fails loudly on the first CI run (not a silent miss).
- All heavy compute is CI-only (no local `ato build`/KiCad/freerouting).

## Rollout

Two branches/PRs off trunk, merged on green, per the repo cadence.
