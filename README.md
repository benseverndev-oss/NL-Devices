# NL-Devices

Natural-language → **validated** electronic schematic/netlist + BOM, eventually a
routed PCB exportable to fab (PCBWay/JLCPCB).

An LLM orchestrator composes **pre-verified subcircuit blocks** (not synthesis from
scratch), validated against a ground-truth component database, with deterministic
compile-to-netlist and verification. The product is *correctness*; natural language
is the interface.

## Docs

- **[DESIGN.md](./DESIGN.md)** — product thesis, target architecture, and the
  adopt/build/avoid decisions.
- **[BUSINESS.md](./BUSINESS.md)** — monetization & business-model strategy
  (the layered, sequenced revenue model).
- **[RESEARCH.md](./RESEARCH.md)** — cited prior-art & competitive research with
  confidence levels behind every decision.

> Status: early scoping / pre-build.
