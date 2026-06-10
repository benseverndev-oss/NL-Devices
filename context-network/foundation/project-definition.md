# Project Definition

## What it is
**NL-Devices** turns a natural-language device description into a **validated**
electronic design — schematic/netlist + a manufacturable BOM, and (now) a **routed,
DRC-clean PCB** exportable to fab. An LLM orchestrator **composes pre-verified
subcircuit blocks** (it never synthesizes connectivity from scratch); every output is
checked against a ground-truth component database and a deterministic seam-validator
before it is shown.

> **Thesis: `validated` is the product, `NL` is the interface, the trust layer is the
> moat.** The generative NL→schematic front-end is commoditizing; the defensible work is
> everything around the LLM (verified blocks, seam validation, manufacturable part data).
> See [`DESIGN.md`](../../DESIGN.md), [`RESEARCH.md`](../../RESEARCH.md).

- **GitHub:** `benseverndev-oss/NL-Devices` (auth as personal `benzsevern`, **public** repo).
- **Substrate:** atopile (`.ato`) compiles typed blocks → KiCad netlist/PCB; a custom
  permissive seam-validator owns correctness; ngspice (BSD) for honest electrical sims;
  freerouting (reference autorouter) + KiCad CLI for routing → copper.

## The governing arc (current)
**Close the four pillars of the goal, honestly.** The validator and the
compile-to-manufacturable-BOM path are real and proven. The autoroute → routed-copper
→ fab pillar is now closed for one vertical (PR #8, [decisions/0003](../decisions/0003-own-the-autoroute.md)).
The honest distance on the remaining pillars (NL proven only on a tiny catalog; block-library
breadth; business assumptions untested) is tracked in [`GAPS.md`](../../GAPS.md).

## Authoritative detail lives elsewhere
This node is deliberately thin. The thesis/architecture/strategy live in the root design
docs ([`DESIGN.md`](../../DESIGN.md), [`GAPS.md`](../../GAPS.md), `SPEC-*.md`); per-gap
implementation lives in those specs + [`docs/superpowers/plans/`](../../docs/superpowers/plans/).
See [structure.md](structure.md).

---
**Classification:** foundation/stable • **Last updated:** 2026-06-09
