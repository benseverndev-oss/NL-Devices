# 0001 — Validation is the product; the LLM composes, never synthesizes

**Status:** accepted (founding thesis) • **Human sign-off:** Ben

## Context
The generative "NL → schematic" front-end is both commoditizing (foundation models,
multiple funded competitors) and not good enough yet (Flux's own founder concedes LLMs are
weak at schematics). Competing on raw NL generation is a losing position.

## Decision
The defensible work is everything *around* the LLM. The LLM is an **orchestrator that
composes pre-verified subcircuit blocks**, not a synthesizer of connectivity. Every output
is checked against a ground-truth component database and a deterministic seam-validator
before it is shown. **Sell correctness + manufacturability; NL is the UX.**

Three things are BUILD (the IP): the verified block library, the seam/electrical-rule
validator (no permissive standalone ERC engine exists — KiCad's is GPLv3), and the
datasheet→structured-data extraction pipeline. AVOID: building on Digi-Key/Mouser APIs
(ToS forbid it), competing on NL chat, building our own DSL.

## Consequences
- The validator ([../architecture/seam-validator.md](../architecture/seam-validator.md)) and
  part DB ([../architecture/ground-truth-partdb.md](../architecture/ground-truth-partdb.md))
  are the moat; the NL planner is enum-constrained to the verified catalog so it cannot
  invent parts ([../architecture/nl-orchestrator.md](../architecture/nl-orchestrator.md)).
- Autorouting was originally AVOID for the same "don't reinvent" reason — later qualified
  ([0003](0003-own-the-autoroute.md)).

## Source
[`DESIGN.md`](../../DESIGN.md) §1–§4, [`RESEARCH.md`](../../RESEARCH.md).

---
**Classification:** decision/accepted • **Last updated:** 2026-06-09
