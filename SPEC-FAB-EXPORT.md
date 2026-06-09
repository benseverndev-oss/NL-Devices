# Spec — Spike One Fab-Export Path

> Addresses [`GAPS.md`](./GAPS.md) §4e / §5 item 7: *"no fab export (Gerbers, JLC/PCBWay
> order API, assembly) — the README's 'routed PCB exportable to fab' is entirely future
> work."* This spikes **one** path end to end and is explicit about the single piece
> that is genuinely upstream (routing).

## What it produces (`spike/fab_export.py`)

From a validated slice + the verified blocks + the ground-truth snapshot, `build_package`
writes a JLCPCB-shaped manufacturing package:

| File | Content | Real now? |
|---|---|---|
| `*-bom.csv` | JLCPCB BOM: `Comment, Designator, Footprint, LCSC Part #` | ✅ every line a real LCSC part (this is where GAPS #1/#3 pay off) |
| `*-cpl.csv` | JLCPCB centroid: `Designator, Mid X, Mid Y, Layer, Rotation` | ⚠️ coords from a deterministic auto-place sized by each part's **real body** (parsed from the snapshot package); **placement is a pre-routing placeholder** |
| `*-Edge_Cuts.gbr` | RS-274X board outline (rectangle, bounding box + margin) | ✅ format-valid Gerber |
| `*.drl` | Excellon drill: 4× M3 mounting holes | ✅ format-valid Excellon |
| `*-manifest.json` | package summary + provenance + the honesty notes | ✅ |

**Copper layers are not emitted.** Routing is the upstream gap (§4e); we don't fake
routed copper. The *mechanical* outline + drill **are** legitimately derivable now, so
those are real; everything that needs a routed layout is flagged, not faked.

## The order path (dry-run)

`build_jlcpcb_order(pkg)` assembles the JLCPCB assembly-order request — PCB specs
(layers, size from the real board bbox, qty, material), the assembly part list (every
real LCSC code + designator), and the file set. It is **`submit: False` by
construction.** Placing an order is a real, paid transaction; this spike never POSTs.
A real submission would need JLCPCB API credentials and an explicit opt-in.

## Validation (`validate_package`, reads the emitted files)

The gate re-reads the written files (not just memory) and rejects a package when:
- a BOM part's LCSC code isn't in the ground-truth snapshot, or is out of stock;
- BOM and CPL designators disagree;
- a required file is missing/empty;
- the Gerber isn't structurally valid RS-274X, or the drill isn't valid Excellon.

This reuses the **same ground-truth snapshot** as `verify_parts` — so a board can't be
sent to fab with a part the trust layer wouldn't pass.

## Verification

`fab_export.py --selftest` (in CI, offline): builds the `sensor_node` package (3 real
parts → 32×32mm board, 5 files), validates it clean, assembles the dry-run order, and
proves the gate **rejects** a package with a bogus LCSC code. `python3 fab_export.py
--out build/fab` writes a real package to the (git-ignored) build dir.

## Honest scope / what's next

- **Routing is the blocker** for real Gerbers (copper layers, real placement). This
  spike proves the *packaging + order mechanics* and the BOM/CPL, not a routed board.
  Wiring in `ato build`'s `.kicad_pcb` + an autorouter + `kicad-cli` Gerber export is
  the §4e step that makes the copper real.
- Placement is a naive grid, not DFM-aware (courtyard spacing, thermal, edge keep-out).
- The order client builds the payload but doesn't authenticate or submit — by design.
