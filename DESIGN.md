# NL-Devices — Design & Strategy

> Natural-language → **validated** electronic schematic/netlist + BOM, eventually
> routed PCB exportable to fab (PCBWay/JLCPCB).
>
> This doc captures the product thesis, architecture, and the adopt/build/avoid
> decisions derived from the prior-art research in [`RESEARCH.md`](./RESEARCH.md).
> Status: **early scoping / pre-build.**

---

## 1. Thesis (revised after research)

The research forces one clarifying reframe:

> **`validated` is the product. `NL` is the interface. The moat is the trust layer.**

The generative "NL → schematic" front-end is both **commoditizing** (foundation
models, multiple funded competitors) and **not good enough yet** (Flux's own
founder concedes LLMs are weak at schematics; users report poor ROI). The hard,
defensible work is everything *around* the LLM:

1. **Verified building blocks** — a library of pre-validated subcircuits.
2. **Seam validation** — checking that blocks connect correctly (an *open research
   problem*, per TypedSchematics arXiv 2509.14576).
3. **Manufacturable component data** — accurate pinouts/ratings/footprints tied to
   real, in-stock parts.

The LLM is an **orchestrator that composes pre-verified blocks**, not a synthesizer
of circuits from scratch. Every output is checked against a ground-truth component
database and a deterministic rule engine before it is shown to the user.

### Positioning
Not "NL → PCB magic," but **"verified, manufacturable circuits from reusable blocks
— described in natural language."** We sell correctness + manufacturability; NL is
the UX.

---

## 2. Target wedge

**First wedge:** `NL → validated schematic/netlist + BOM` (no autorouting yet).

**Likely customer (to be validated):** competent hardware *product teams / startups*
building IoT-class boards (sensor nodes, motor drivers, power supplies) who want
speed **and** a correctness guarantee — not pure hobbyists (won't pay) and not
conservative enterprise EE (won't trust AI yet).

**Vertical-first:** pick one device class, pre-verify its block library end-to-end,
and credibly *guarantee* correctness to non-experts. Breadth comes later.

---

## 3. Architecture (target)

```
  Natural language spec
          │
          ▼
  ┌─────────────────────┐
  │  LLM Orchestrator   │  composes blocks; does NOT invent connectivity
  └─────────┬───────────┘
            │ selects + parameterizes
            ▼
  ┌─────────────────────┐     ┌──────────────────────────┐
  │ Verified Block Lib  │◄────│  Ground-truth Part DB     │
  │ (pre-validated       │     │  (pinouts, ratings,       │
  │  subcircuits + ports)│     │   footprints, stock)      │
  └─────────┬───────────┘     └──────────────────────────┘
            │ compose
            ▼
  ┌─────────────────────┐
  │ Compile → netlist   │  deterministic (atopile / SKiDL substrate)
  └─────────┬───────────┘
            │
            ▼
  ┌─────────────────────┐
  │ Validation engine   │  seam/ERC rules + SPICE (ngspice) sanity checks
  │  (the moat)         │  → PASS/FAIL with explanations
  └─────────┬───────────┘
            │ on PASS
            ▼
   Schematic + netlist + BOM  ──►  (later) layout/route  ──►  fab export
```

**Key principle:** the LLM never emits raw connectivity that bypasses validation.
It chooses and wires *typed, pre-verified blocks*; the compiler and validator are
deterministic and own correctness.

---

## 4. Adopt / Build / Avoid decisions

### ✅ ADOPT (don't reinvent)
| What | Choice | Rationale |
|---|---|---|
| Compile-to-netlist substrate | **atopile** (MIT, DSL + constraint solving + part-picking + KiCad output) **or** **SKiDL** (MIT, pure-Python, trivial embed) | Two mature MIT options; building a DSL is wasted effort. atopile = ambition; SKiDL = lowest-risk embed. **Spike both early.** |
| Simulation | **ngspice** (**BSD** — safe to embed) | PySpice/KiCad-ERC are GPLv3; ngspice is permissive |
| Seed component data | **jlcparts** pipeline (MIT) + **KiCad / SnapEDA / Octopart CPL** libs (CC-BY-SA) | jlcparts ties parts to *real JLCPCB stock* = manufacturability for free |
| CAD symbols/footprints | Open CC-BY-SA libs (mind ShareAlike only on *redistribution*) | Genuinely open and reusable in commercial designs |

### 🔨 BUILD (this is the IP)
| What | Why it's defensible |
|---|---|
| **Verified building-block library** (typed subcircuits + port contracts) | The moat thesis — but the *least proven* leg; de-risk early |
| **Seam / electrical-rule validator** | **No permissive standalone ERC engine exists** (KiCad's is GPLv3). Building one is necessary *and* defensible |
| **Datasheet → structured-data extraction pipeline** | No licensable shortcut for parametric/pinout data without redistribution limits; SOTA ~86% extraction → human-in-the-loop review |

### ⛔ AVOID
| What | Why |
|---|---|
| Building a parts DB from **Digi-Key / Mouser APIs** | ToS *forbid* "creating your own database" + delete-on-termination. Use only as live display/pricing feeds |
| Competing on raw **NL chat / generation** | Commoditizing; even insiders say it's not the moat |
| **Autorouting** (for now) | Quilter / Cadence Allegro X AI / Freerouting own it. **Complement** them — feed Quilter our validated netlist |
| Building our own **DSL** | atopile/tscircuit/SKiDL already exist under MIT |

---

## 5. Competitive position (one-liner each)

- **Flux.ai** — most direct (full-flow NL→BOM, ~$59M, 1.1M users) but synthesis
  quality unproven; recent trust hit. *Differentiate on validation/guarantee.*
- **Diode** — closest twin (code-based + manufacturing, YC/a16z). *Watch closely.*
- **CELUS** — block library ("CUBOs") but quiet since 2022. *Our clearest precedent.*
- **Quilter** — placement/routing only, not LLM. *Complementary — integrate, don't fight.*
- **Altium/Renesas, Cadence, Zuken** — incumbents bolting AI onto existing flows;
  own supply chain + install base. *Avoid head-on; win on NL-native + guarantee.*

---

## 6. Open risks (must de-risk before committing)

1. **Verified-block-library as a business is unproven** (only CELUS, venture-stage).
   The inter-block connection problem is an open research question. → **Build a thin
   vertical slice and prove block-composition validation works.**
2. **Monetization vise** — NL-wanting segment won't pay; paying segment won't trust.
   The proven model is **manufacturing integration** (free tool → fab/parts margin,
   à la JLC/EasyEDA $273M). → **Treat fab integration as a first-class business-model
   candidate, not a late feature.**
3. **Data moat is expensive + partly legally boxed in** (~86% extraction ceiling →
   human review; distributor APIs closed). → **Bootstrap from open + JLC data;
   negotiate Nexar/Octopart with ML-training rights in writing if needed.**

---

## 7. Immediate next steps

1. **Spike the substrate:** prototype the same 1–2 simple boards in both **atopile**
   and **SKiDL**; pick one.
2. **Define the block contract:** what is a "verified block"? (ports, electrical
   constraints, parameter ranges, validation metadata.)
3. **Prove seam validation** on a single vertical (e.g. an MCU + sensor + power
   block) — this is the riskiest/most-defensible piece.
4. **Stand up seed part data** from jlcparts + KiCad/SnapEDA libs.
5. **Customer discovery** against the monetization risk: would the target team pay,
   and for what (the tool, the guarantee, or the one-click fab)?

> See [`RESEARCH.md`](./RESEARCH.md) for the full cited evidence base and confidence
> levels behind every decision above.
