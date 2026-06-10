# Structure

## Repo layout
- **`spike/`** — the running prototype: flat Python modules (the validator, part DB, NL
  orchestrator, electrical sims, fab export, routing pipeline). This is where everything
  actually runs. See the [architecture/](../discovery.md) nodes.
  - `spike/blocks/*.yaml` — block contracts; `spike/atopile/*.ato` — the atopile sources
    (`verified_slice.ato:App` is the real routed board; `sensor_node.ato:App` is a passive
    demo stub — [decisions/0004](../decisions/0004-route-the-verified-board.md)).
  - `spike/atopile/elec/src/parts/**` — per-part libs (footprint + symbol + **committed
    3D model**, [decisions/0005](../decisions/0005-commit-3d-models.md)).
  - `spike/fixtures/verified/` — the committed unrouted board + parser fixtures the offline
    tests run against.
  - `spike/scripts/kicad_specctra.py` — pcbnew DSN/SES helper (runs under KiCad system python).
- **Root design docs** — the authoritative narrative layer (this repo has **no `CLAUDE.md`**;
  the root `*.md` docs play that role):
  - [`DESIGN.md`](../../DESIGN.md) thesis/architecture/adopt-build-avoid · [`GAPS.md`](../../GAPS.md)
    the honest gap audit · [`BUSINESS.md`](../../BUSINESS.md) · [`RESEARCH.md`](../../RESEARCH.md)
    · [`DECISION.md`](../../DECISION.md) substrate memo · [`ORCHESTRATOR.md`](../../ORCHESTRATOR.md)
    · [`SPIKE.md`](../../SPIKE.md).
  - `SPEC-*.md` — one per closed gap (PARTDB, VALIDATOR-DEPTH, SPICE, NL-PLANNER, FAB-EXPORT,
    ROUTING). Implementation plans under [`docs/superpowers/plans/`](../../docs/superpowers/plans/).
- **`scripts/`** — `setup.sh`/`.ps1` (pinned toolchain install) + `check_toolchain.py`
  (offline pin-consistency lint, incl. KiCad/freerouting pins).
- **`.github/workflows/ci.yml`** — 3 jobs (`spike`, `toolchain`, `route`); see
  [processes/development-workflow.md](../processes/development-workflow.md).

## Toolchain pins
**atopile 0.12.5 / Python 3.13** ([decisions/0002](../decisions/0002-pin-atopile-0.12.5.md)),
KiCad 9, freerouting 2.1.0 (needs **Java 21**). None are installed on the maintainer's
Windows box — CI (ubuntu) runs the real tools.

---
**Classification:** foundation/stable • **Last updated:** 2026-06-09
