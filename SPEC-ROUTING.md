# Spec — Own the Autoroute: Routed Copper → Fab

> Closes [`GAPS.md`](./GAPS.md) §4e / §5 item 7's remaining 🔴: *"`ato build` emits a
> `.kicad_pcb` with components but no placement/routing — still the load-bearing gap …
> copper layers aren't emitted."* [`SPEC-FAB-EXPORT.md`](./SPEC-FAB-EXPORT.md) spiked the
> packaging + order mechanics around a **copper-less** board; this spec produces the
> copper: a genuinely **routed, DRC-clean** `sensor_node` board exported to real Gerbers.
>
> **This reverses a prior decision.** [`DESIGN.md`](./DESIGN.md) §4 lists autorouting under
> **⛔ AVOID** ("Quilter / Cadence own it. *Complement* them"). We are moving it to a
> **qualified BUILD** — see [§7](#7-the-strategy-reversal-design-4). The complement-Quilter
> thesis survives: production routing swaps in through the same `.dsn`/`.ses` seam.

## 1. The board being routed

The `sensor_node` slice composes three verified blocks — `power_3v3_ldo` (AMS1117-3.3,
SOT-223), `mcu_i2c_controller` (STM32F103C8T6, LQFP-48), `sensor_eeprom_24c256` (SOIC-8) —
plus the passives the atopile blocks expand (VDD/VBAT/VDDA decoupling, the NRST reset RC,
the BOOT0 strap, I2C1 pull-ups). `ato build` emits the full netlist; we route **that**, not
the 3-IC abstraction the Python BOM tracks. **2-layer** board (F.Cu / B.Cu).

## 2. The pipeline

One new stage chain, run in CI, every box a real tool invocation:

```
ato build  (CI, network LCSC part-pick)  ─►  sensor_node.kicad_pcb   (footprints, unplaced)
  ─► place.py            deterministic placement, written into the .kicad_pcb
  ─► kicad-cli export     Specctra .dsn   (carries the net-class clearances/widths)
  ─► freerouting.jar      headless autoroute  →  .ses     [assert 0 unrouted]
  ─► kicad-cli import     .ses  →  routed .kicad_pcb
  ─► kicad-cli pcb drc    →  DRC report      [assert 0 violations]
  ─► kicad-cli export     Gerbers + Excellon drill (all layers, real copper)
  ─► fab_export.py        assemble the JLCPCB package around the real copper + routed CPL
```

Two unifications fall out of this:

- **Placement becomes the single source of truth.** `fab_export` today invents a throwaway
  grid placement just for the CPL; after this, the CPL coordinates **are** the routed
  board's coordinates (read back from the routed `.kicad_pcb`).
- **`kicad-cli`'s Gerber/drill export replaces the hand-rolled `*-Edge_Cuts.gbr` / `*.drl`**
  in `fab_export`. A real export from a real board beats a hand-authored outline, and it
  now carries copper layers, soldermask, paste, and silk — not just the mechanical outline.

## 3. Modules (isolation)

| Module | Role | Runs where | Testable offline? |
|---|---|---|---|
| `spike/place.py` | **Pure.** Deterministic placement: reuses `fab_export`'s body-size logic, courtyard-spaced, decoupling caps kept adjacent to their owner. In: parts + body sizes + nets. Out: `{refdes: (x, y, rot, layer)}`. | offline `--selftest` + CI | ✅ no KiCad dependency |
| `spike/route.py` | **Thin tool orchestration.** Shells `ato` / `kicad-cli` / `java -jar freerouting.jar`; **parses** their outputs (unrouted-net count, DRC JSON, Gerber file set). Parsers are pure. | CI (tools); parsers offline | ⚠️ tool calls CI-only; parsers ✅ |
| `spike/fab_export.py` | **Extended.** Ingests real copper + routed placement; drops the placeholder grid + hand-rolled outline; `--selftest` asserts copper layers present. | offline + CI | ✅ (against captured fixtures) |

Everything that can't run on a dev box (the tool invocations) sits behind thin wrappers;
everything that can (placement math, output parsing) is pure and unit-tested offline — the
same discipline `spice_sim.py` uses to cross-check its analytic limit without ngspice
locally.

## 4. How DRC-clean is guaranteed (not hoped for)

A routed board is only DRC-clean if the autorouter routes to the *same* rules KiCad checks.
So the board declares **one explicit net class** (default: 0.2 mm track / 0.2 mm clearance /
standard via) before DSN export; the `.dsn` carries those rules; freerouting routes to them;
the result passes `kicad-cli pcb drc` by construction. The residual DRC risks are therefore
**not** clearance — they are:

- **courtyard overlap** → owned by `place.py` (spacing ≥ courtyard + margin);
- **edge clearance** → owned by the computed board outline (bbox + margin, from `fab_export`);
- **unrouted nets** → gated *separately* on freerouting's completion count.

## 5. BOM / CPL reconciliation

The routed `.kicad_pcb` has more footprints than the 3-line snapshot BOM (it includes
atopile-expanded passives). Rules:

- **CPL** is generated from the routed board's footprint positions — every placed footprint,
  including passives.
- **BOM** still comes from the `verify_parts` ground-truth snapshot for the bound ICs;
  passives are atopile-picked generics. The validator already flags that the snapshot does
  **not** pin the `ato build` part-pick (GAPS §4d) — so this spec does **not** claim the
  passives are ground-truth-verified. The package gate asserts BOM ⊆ board designators and
  that every *bound* IC reconciles to the snapshot; un-snapshotted passives are reported, not
  blessed.

## 6. CI

A **new `route` job**, isolated from the deterministic `spike` job so its network + heavy-tool
fragility can't redden the core gates:

- installs a **pinned KiCad** (exposing `kicad-cli pcb export specctradsn` / SES import —
  KiCad 9; falls back to a `pcbnew` Python script if a subcommand is absent), **java**, and a
  **pinned `freerouting` release** (jar by tag);
- runs `ato build` (the accepted fragile network step) → the full chain in §2;
- **hard-fails** on: unrouted ≠ 0, DRC ≠ 0, or missing/invalid copper Gerbers.

KiCad + freerouting versions are pinned, matching the project's pin-everything ethos
(`check_toolchain.py` is extended to lint the new pins). `place.py` and the `route.py`
parsers also run in the existing offline `spike` job via `--selftest`, so the pure logic is
gated even when the `route` job is skipped/red.

## 7. The strategy reversal (DESIGN §4)

`DESIGN.md` §4 moves: autorouting **⛔ AVOID → 🔨 BUILD (qualified)**, with this rationale,
written into the doc rather than left as a silent contradiction:

> We own a **reference** autoroute path (freerouting, headless) to make "routed PCB → fab"
> *real* for the one vertical — the 🔴 that blocked the ultimate goal. This does not mean
> competing with Quilter/Cadence on routing quality at scale: the `.dsn` export / `.ses`
> import is a **seam**, and a production-grade router (Quilter) swaps in at exactly that
> boundary. "Complement, don't fight" holds; we just stopped having *zero* routing.

`GAPS.md` §4e/§5.7 is updated to reflect the 🔴 closing for `sensor_node`, and the README doc
list gains `SPEC-ROUTING.md`.

## 8. Verification / acceptance

Done = on the `sensor_node` board, in CI:

1. `ato build` produces the netlisted `.kicad_pcb`;
2. `place.py` places it (courtyard-safe, offline-tested);
3. freerouting reaches **0 unrouted nets**;
4. `kicad-cli pcb drc` reports **0 violations**;
5. real copper Gerbers + Excellon drill export and are **format-valid**;
6. `fab_export --selftest` asserts the package now carries **copper layers** + a **routed
   CPL**, and still rejects a bogus-LCSC package (the existing gate);
7. `place.py` + the `route.py` output parsers pass **offline** `--selftest` in the `spike` job.

## 9. Honest scope / what's next

- **One board, one vertical.** This routes `sensor_node` (3 ICs + passives) on 2 layers. It
  does not claim a general autorouter; breadth (a second slice, 4-layer, controlled impedance)
  is out of scope.
- **Placement is deterministic, not DFM-optimal.** Courtyard-safe and caps-near-pins, enough
  to route DRC-clean — not thermal-, EMI-, or yield-optimized. A real placer (or Quilter's) is
  the higher-fidelity swap-in.
- **Network on the CI critical path.** `ato build`'s LCSC part-pick is the known-fragile step
  (GAPS §4d); isolating it in its own job contains the blast radius but doesn't remove it.
  Pinning the part-pick to the snapshot for a fully offline build remains the open §4d item.
- **Passives aren't ground-truth-verified** (§5) — they ride atopile's generic part-pick, not
  the snapshot. Consistent with the existing GAPS §4d caveat; not newly claimed here.
- **If freerouting can't reach 0/0**, the hard gate keeps CI red until placement or board
  params are tuned — by design (the accepted acceptance bar).
