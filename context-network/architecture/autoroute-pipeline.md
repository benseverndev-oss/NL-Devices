# Autoroute Pipeline (routed copper → fab)

**SHIPPED — PR #8, 2026-06-09.** Closes the `GAPS.md` §4e routing 🔴 for one real board:
turns the `ato build` netlist into **routed, DRC-clean copper Gerbers**, folded back into
the JLCPCB fab package. Runs in the CI `route` job, hard-gated on every push.

## The pipeline (CI `route` job)
```
ato build -b verified
  → place.py            courtyard-safe placement + Edge.Cuts outline (pure s-expr, offline-tested)
  → pcbnew ExportSpecctraDSN
  → freerouting          headless autoroute (.dsn → .ses)
  → pcbnew ImportSpecctraSES → routed .kicad_pcb
  → kicad-cli pcb drc    (json)
  → kicad-cli export gerbers + drill   → real F.Cu/B.Cu/Edge.Cuts copper
  → fab_export.build_routed_package    BOM + CPL from the routed board + real copper
```
**HARD GATE:** 0 unrouted nets · 0 DRC violations · format-valid copper layers · clean package.

## Modules (`spike/`)
- `place.py` — pure: parse footprints from the `.kicad_pcb` s-expr (no pcbnew), grid-place
  courtyard-safe, stamp an Edge.Cuts rectangle, write `(at …)` back. Offline `--selftest`.
- `route.py` — pure output parsers (`parse_unrouted`, `parse_drc`, `gerber_layers_present`,
  offline-tested) + tool-orchestration wrappers + `pipeline()`.
- `scripts/kicad_specctra.py` — pcbnew DSN export / SES import (the round-trip `kicad-cli`
  can't do); runs under KiCad's **system python**.
- `fab_export.build_routed_package` — the routed board is the single source of truth for
  BOM + CPL; bound ICs reconcile to the part snapshot, atopile-picked passives are reported.

## Hard-won toolchain facts (the iteration cost is paid; don't re-learn)
- **`kicad-cli` has NO Specctra path** → use `pcbnew.ExportSpecctraDSN(board, f)` /
  `ImportSpecctraSES(board, f)` under `/usr/bin/python3` (pcbnew isn't in the 3.13 venv).
- **freerouting 2.1.0 needs Java 21** (`actions/setup-java@v4` temurin 21; `default-jre`=17
  fails class-file 65). Headless CLI:
  `java -Djava.awt.headless=true -jar freerouting.jar -de IN.dsn -do OUT.ses -mp 100`.
  Completion is the JSON `"incomplete_count": N` (NOT `unrouted: N`).
- `kicad-cli pcb drc --format json --severity-error --exit-code-violations`;
  `pcb export gerbers -o DIR --layers F.Cu,B.Cu,… IN` + `pcb export drill`.
- The `ato build` board has **no Edge.Cuts geometry** (only the layer) — `place.add_outline`
  must add a boundary or freerouting/DRC have nothing to bound.

## The board
`verified_slice.ato:App` — AMS1117-3.3 LDO (C6186) + AT24C256 EEPROM (C6482) + decoupling +
I2C pull-ups: 7 footprints, 5 nets (SCL/SDA/3V3/5V/GND). Chosen over the `sensor_node` stub —
[decisions/0004](../decisions/0004-route-the-verified-board.md).

## Honest scope
One board / one vertical / 2 layers; deterministic (not DFM-optimal) placement; `ato build`'s
LCSC part-pick still hits the network (isolated in the `route` job). The reference router is
freerouting; a production router (Quilter) swaps in at the `.dsn`/`.ses` seam
([decisions/0003](../decisions/0003-own-the-autoroute.md)).

## Source of truth / specs
[`SPEC-ROUTING.md`](../../SPEC-ROUTING.md), plan at
[`docs/superpowers/plans/2026-06-09-autoroute-copper.md`](../../docs/superpowers/plans/2026-06-09-autoroute-copper.md),
[`GAPS.md`](../../GAPS.md) §4e. Fab package: [`SPEC-FAB-EXPORT.md`](../../SPEC-FAB-EXPORT.md).

---
**Classification:** architecture/active • **Last updated:** 2026-06-09
