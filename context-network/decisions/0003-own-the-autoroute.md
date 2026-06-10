# 0003 — Own the autoroute (reverse DESIGN §4 AVOID → qualified BUILD)

**Status:** accepted + shipped (2026-06-09, PR #8) • **Human sign-off:** Ben, 2026-06-09

## Context
A skeptical re-audit of [`GAPS.md`](../../GAPS.md) found that routing — `ato build` emits a
`.kicad_pcb` with no placement/routing, fab copper is a placeholder — is the project's real
🔴, not the 🟠 the doc rated it. It's the one thing that turns a netlist tool into a board
you can order. `DESIGN.md` §4 had listed autorouting under ⛔ AVOID ("Quilter/Cadence own
it; complement them").

## Decision
Reverse §4: autorouting moves to a **qualified BUILD**. Own a **reference** autoroute path
(freerouting, headless) to make "routed PCB → fab" real for one vertical. This is **not**
competing with Quilter/Cadence on routing quality at scale — the Specctra `.dsn`/`.ses`
export is a **seam** where a production router (Quilter) swaps in. "Complement, don't fight
at scale" still holds; we just stopped having *zero* routing. The reversal is written into
`DESIGN.md` §4, not silent.

## Consequences
- New CI `route` job + modules ([../architecture/autoroute-pipeline.md](../architecture/autoroute-pipeline.md))
  hard-gated on 0 unrouted + 0 DRC + format-valid copper.
- Forced sub-decisions: route the `verified` board not the stub ([0004](0004-route-the-verified-board.md));
  commit the 3D models ([0005](0005-commit-3d-models.md)).
- Toolchain facts (freerouting Java 21, pcbnew Specctra, kicad-cli) captured in the
  architecture node so the iteration cost isn't re-paid.

## Source
[`SPEC-ROUTING.md`](../../SPEC-ROUTING.md), plan
[`docs/superpowers/plans/2026-06-09-autoroute-copper.md`](../../docs/superpowers/plans/2026-06-09-autoroute-copper.md).

---
**Classification:** decision/accepted • **Last updated:** 2026-06-09
