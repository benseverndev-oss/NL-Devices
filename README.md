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
- **[SPIKE.md](./SPIKE.md)** — Phase-0 engineering spike: verified blocks +
  seam validation, and the atopile-vs-SKiDL bake-off. *(Steps 0–6 complete — see
  `spike/`.)*
- **[DECISION.md](./DECISION.md)** — spike decision memo: scorecard + chosen
  substrate/architecture (atopile + custom seam-validator + ngspice harness).
- **[ORCHESTRATOR.md](./ORCHESTRATOR.md)** — NL → validated-design orchestrator
  prototype: composes verified blocks, gated by the seam-validator.
- **[RESEARCH.md](./RESEARCH.md)** — cited prior-art & competitive research with
  confidence levels behind every decision.
- **[GAPS.md](./GAPS.md)** — gap audit: honest distance from the running spike to the
  ultimate goal (verified by executing every component), with prioritized next steps.

> Status: early scoping / pre-build.
