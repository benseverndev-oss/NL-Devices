# 0004 — Route the `verified` board, not the `sensor_node` stub

**Status:** accepted + shipped (2026-06-09, PR #8) • **Human sign-off:** Ben, 2026-06-09

## Context
Mid-build, the routing target `sensor_node.ato:App` turned out to build a **5-passive stub
with no silicon** — its generic `LDO`/`EEPROM` imports never resolve to placed footprints
and `McuBlock` has no MCU. The docs called it an "STM32 + LDO + EEPROM board"; the actual
build had neither (the same docs-overclaim-vs-code gap the audit was about). Routing it
would prove the pipeline plumbing on a meaningless network.

## Decision
Route the **`verified` build** (`verified_slice.ato:App`) instead: real **AMS1117-3.3 LDO**
(C6186) + **AT24C256 EEPROM** (C6482) + decoupling + I2C pull-ups — 7 footprints, 2 real
ICs, a 5V→3V3 rail and an I2C bus. A genuine (if small) place-and-route problem, so
"routed copper → fab" is honest. A known-good build target, low risk.

## Consequences
- The CI `route` job builds `-b verified`; the offline fixture is
  `spike/fixtures/verified/verified.kicad_pcb`.
- The STM32 block exists in the parts lib but isn't wired into any build target — a fuller
  board (MCU + LDO + EEPROM) is a deliberate follow-up, NOT bolted onto the routing work
  (it would be an atopile design change + risks another `ato build` debugging cycle).

## Source
[../architecture/autoroute-pipeline.md](../architecture/autoroute-pipeline.md),
[planning/roadmap.md](../planning/roadmap.md).

---
**Classification:** decision/accepted • **Last updated:** 2026-06-09
