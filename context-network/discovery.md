# Context Network — Discovery Hub

The navigation entry point. Each node below is focused and cross-linked; follow the
links rather than reading everything.

## Foundation (what this is)
- [foundation/project-definition.md](foundation/project-definition.md) — what NL-Devices is, the thesis ("validation is the product"), and the governing arc.
- [foundation/structure.md](foundation/structure.md) — the `spike/` prototype layout, the atopile project, and where the authoritative docs live.

## Architecture (active technical knowledge)
- [architecture/seam-validator.md](architecture/seam-validator.md) — the gate: 7 seam/electrical checks + the adversarial corpus that measures the false-negative rate.
- [architecture/ground-truth-partdb.md](architecture/ground-truth-partdb.md) — the sourced, pinned part snapshot + the offline `verify_parts` gate.
- [architecture/nl-orchestrator.md](architecture/nl-orchestrator.md) — NL → plan → gate; the LLM seam and the honest caveat that the eval runs a `FakeModel`, not a real LLM.
- [architecture/electrical-validation.md](architecture/electrical-validation.md) — analytic LDO-dropout gate + real ngspice `.tran` sims (no SPICE theatre).
- [architecture/autoroute-pipeline.md](architecture/autoroute-pipeline.md) — `ato build` → place → freerouting → DRC → real copper Gerbers → fab package; CI-gated. SHIPPED (PR #8).

## Decisions (records with no other home)
- [decisions/0001-validation-is-the-product.md](decisions/0001-validation-is-the-product.md) — compose pre-verified blocks, never synthesize; NL is the interface, validation is the moat.
- [decisions/0002-pin-atopile-0.12.5.md](decisions/0002-pin-atopile-0.12.5.md) — pin atopile 0.12.5 / Python 3.13 (0.13+ needs py3.14, which crashes).
- [decisions/0003-own-the-autoroute.md](decisions/0003-own-the-autoroute.md) — reverse DESIGN §4: own a *reference* freerouting autoroute behind a Specctra `.dsn`/`.ses` seam; Quilter swaps in.
- [decisions/0004-route-the-verified-board.md](decisions/0004-route-the-verified-board.md) — route the `verified` board (real LDO+EEPROM), not the `sensor_node` passive stub.
- [decisions/0005-commit-3d-models.md](decisions/0005-commit-3d-models.md) — commit the per-part 3D models (~25 MB) so `ato build` is reproducible in CI.

## Processes (how work is done here)
- [processes/development-workflow.md](processes/development-workflow.md) — spec → plan → execute → CI → merge, plus the hard environment constraints (no local heavy compute; CI is the test runner).

## Planning (where it's going)
- [planning/roadmap.md](planning/roadmap.md) — what's next, by leverage.

## Meta (keeping the network alive)
- [meta/updates.md](meta/updates.md) — chronological change log for the network.
- [meta/maintenance.md](meta/maintenance.md) — how to keep nodes accurate and small.

---
**Classification:** navigation • **Last updated:** 2026-06-09
