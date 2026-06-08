# Prior-Art & Competitive Research

> Multi-source, primary-source-prioritized research on the "natural-language →
> validated schematic/netlist + BOM" space. Compiled 2026-06-08.
>
> Confidence tags: **High** = primary/official source or multiple consistent
> sources · **Med** = single secondary source · **Low** = inferred, vendor-
> marketed, or gated/unverified. Items we could not verify are flagged
> explicitly so they are not laundered into false certainty.

---

## 0. Headline finding

The "NL → schematic" generative front-end is **simultaneously commoditizing and
not yet good enough**, while the genuinely hard and defensible problems —
**validation, verified-and-manufacturable component data, and connecting blocks
correctly** — remain unsolved.

- Flux's founder reportedly stated raw foundation models "aren't that useful for
  schematics." (Med — HN 40753768, via search summary; direct fetch rate-limited)
- HN users report burning **$50–100 in tokens** to place a handful of components
  in Flux. (Med — HN 48368721, via summary)
- The block-composition problem is an **open research question**: TypedSchematics
  (arXiv 2509.14576) finds reusable blocks "do not provide clear information on
  how to connect different blocks together." (Med) — this is exactly our
  seam-validation problem.

**Implication:** `validated` is the product; `NL` is the interface. The moat is
the trust layer (validation + manufacturable data), not the LLM.

---

## 1. Circuits-as-code / textual HDL tools (foundation candidates)

| Tool | License | Approach | Maturity | Foundation fit |
|---|---|---|---|---|
| **atopile** (`.ato`) | **MIT** (open-core co.) | Declarative DSL; constraint solving + automatic parametric part-picking; native KiCad output (`.kicad_pcb`, BOM, fab/assembly data) | ~3.4k★, active (push 2026-04-03), YC W24, ~$500k pre-seed | **Best ambitious match.** Purpose-built, MIT, constraint engine + part-picking built in. Risk: custom DSL/toolchain, small team (~3) |
| **tscircuit** | **MIT** | TS/React (React-Fiber renderer) → "Circuit JSON" intermediate; Gerbers, PnP, BOM, KiCad-compatible | ~2.2k★, very active (push 2026-06-08); modular npm packages (autorouter, circuit-json) | Strong; modular and AI-friendly. Risk: React-runtime dependency surface, custom intermediate format; autorouter still maturing |
| **SKiDL** | **MIT** | Python *library* (not a DSL); netlists + hierarchy + ERC; KiCad v5–9, XML BOM, SVG | v2.2.3 (2026-04-08), ~1.5k★, **single maintainer** | **Lowest-risk to embed** (pure Python, no parser). Limited scope: netlist only, no constraint solving / part selection / layout |
| **JITX** | **Proprietary** (product) | "Software-defined electronics"; constraint solver + EM-sim loop; AI codegen; front-end migrated Stanza→Python | Series A $12M (Sequoia, 2022) | **Not a foundation** — closed product. Only the L.B. Stanza language is open (non-standard custom `License.txt`, unverified SPDX) |
| **PHDL** (BYU) | Unverified | Academic HDL → PADS/EAGLE netlists; Java/Eclipse | **Dormant/abandoned**, legacy targets, no KiCad | Poor foundation candidate |

**Verdict:** Adopt **atopile** (ambition) or **SKiDL** (low-risk embed) as the
compile-to-netlist substrate. Don't build a DSL — two mature MIT options exist.

**Flagged/unverified:** L.B. Stanza exact SPDX license (custom file, not read);
JITX output formats (KiCad/Gerber/BOM not documented publicly); JITX Stanza→Python
migration (single blog source); tscircuit funding (none found — likely
bootstrapped); atopile exact pre-seed $ (secondary aggregators).

---

## 2. AI/LLM EDA copilots & generative-PCB startups (competitors)

| Player | Funding | What it does | Threat to our wedge |
|---|---|---|---|
| **Flux.ai / Flux Copilot** | ~$37M disclosed Feb 2026 ($27M B led by 8VC + $10M A); ~$59M total (PitchBook); claims ~1.1M users / 6.4M projects (self-reported) | Browser eCAD; NL prompt → schematic → AI auto-layout → routing → manufacturing; live part pricing. Uses foundation-model LLMs (vendor unnamed) | **Most direct.** But synthesis quality unproven; poor user ROI reported; trust hit (Adafruit legal-letter incident, June 2026) |
| **Diode Computers** (pcb.new) | YC S24; ~$11.4M A led by a16z, ~$15M total (secondary sources) | Code-based / composable modules; AI generates reusable modules; pcb.new + pcb.store (order/mfg). Customers: Physical Intelligence, Saronic | **Closest philosophical twin** — code-based full flow + manufacturing. Watch closely |
| **CELUS** | ~€25M A (2022, Earlybird); **no news since** | Requirements → auto-generated schematic blocks ("CUBOs") + part selection; exports to user's EDA. Claims up to 90% design-time reduction | Overlaps block thesis; likely predates LLM wave (rules/ML); possibly stalled |
| **Quilter** | ~$40M (Benchmark A $10M 2024; Index B $25M Oct 2025) | **Placement & routing only** (physics RL + neural nets, "thousands of candidate boards"); explicitly **not an LLM**. Ingests Altium/Cadence/Siemens/KiCad schematics → fab-ready layout. ~100–1,000 components | **Complementary, not competitive** — feed it our netlist |
| **Cadence Allegro X AI** | Public | Generative placement/routing/power-plane; physics-based; claims ~10x turnaround, ~12% wire-length improvement. **Not schematic synthesis** | Layout incumbent; complementary |
| **Altium (= Renesas, acq. Aug 2024)** | Public | Renesas 365 on Altium platform; ML in flows; Octopart supply-chain; acquired Part Analytics (2025) | **Largest strategic threat** — silicon + supply chain + install base |
| **Zuken CR-8000 2025** | Public | AI placement/routing/verification; "Design Gateway Copilot" for schematic-assist (connection-pattern recognition, partial-net completion) | Closest incumbent to schematic-assist |

**Flagged/unverified:** Diode "Nexus" product name — **no source found** linking
it to Diode (wrong/internal/confused). Diode funding via secondary sources only.
Quilter Series-B total ($40M) + Lip-Bu Tan angel from secondary sources. No
vendor publicly names its foundation model.

**Academic NL→schematic (still research-stage):** SchGen, pcbGPT, PCBSchemaGen
(arXiv 2606.x / 2602.x preprints, 2026) — data scarcity cited as the key blocker.
(Med — preprints, not peer-reviewed.)

---

## 3. Component-data layer (the hypothesized moat)

### Can't build a DB from distributor APIs — ToS forbids it
- **Digi-Key:** explicitly prohibits using the API/data "to update or create your
  own database"; no third-party redistribution without written approval. (High)
- **Mouser:** same "no database" clause + no aggregation + **must delete all data
  on termination** → unusable as a durable owned asset. (High)
- Neither agreement affirmatively permits ML/AI training (Digi-Key silent → not
  permitted given the bans). (Med)

### Nexar / Octopart (Altium) — the one negotiable licensed source
- Octopart API folded into **Nexar GraphQL API** (old REST = "Legacy"). (High)
- Tiers: Evaluation (free, ~100–1,000 matched-parts lifetime), Standard (~2,000/mo),
  Pro (~15,000/mo), Enterprise (custom). **Dollar pricing is gated/unverified.** (High limits / Low price)
- Billed per returned **supply** part object; design queries don't count. (High)
- Governed by negotiated "ordering documents"; **redistribution / ML-training /
  caching clauses are JS-gated and unverified — must confirm in contract.** (Low)

### CAD/symbol/footprint layer — genuinely open and reusable
- **SnapEDA/SnapMagic:** symbols/footprints/3D under **CC BY-SA 4.0 + Design
  Exception** → no attribution when used *inside* manufactured designs; attribution
  only when the *library/CAD files* are redistributed publicly. Search API exists
  (free + Premium; pricing gated). (High)
- **KiCad official libs:** CC-BY-SA 4.0 + Design Exception (waives ShareAlike for
  designs/generated files) → usable in proprietary/commercial work; redistributing
  the *library itself* still triggers CC-BY-SA + attribution. (High)
- **Octopart Common Parts Library (CPL):** CC BY-SA 4.0. (High)
- **CERN** KiCad library (~17k components): CERN-OHL Permissive. (Med)
- **Ultra Librarian:** 16M+ symbols/footprints/3D, free download in 20–30+ formats,
  but terms grant use *within* ECAD only — not for building a competing library. (Med)

### Manufacturing-tied free seed data
- **jlcparts** (yaqwsx, **MIT** code): periodically ingests JLCPCB's assembly CSV →
  per-category JSON parametric search. Data remains LCSC's; CSV availability has
  been intermittently broken. (High) — ties parts to **actual JLCPCB stock** =
  manufacturability signal for free.
- **LCSC:** no official API (scrape, ~100 req/min). EasyEDA library ~700k parts. (Med)

### Datasheet → structured data is feasible but lossy (→ human review needed)
- **D2S-FLOW** (arXiv 2502.16540): LLM datasheet→SPICE extraction, **Exact-Match
  0.86, F1 0.92**. Best-case ~86% → residual errors remain. (High)
- **PINS100 / "From Words to Wires"** (arXiv 2305.14874): raw LLM pinout knowledge
  ~**55–74% strict / 74–86% permissive** → unreliable. (Med)
- **DocEDA** (2412.05301), **ModelGen** (ACM TODAES 2025): active, partially-solved
  extraction pipelines. (High/Med)

**Strategic verdict:** A proprietary structured DB realistically means **(a)** owning
the datasheet-extraction pipeline (no usable licensed shortcut for parametric/pinout
without redistribution limits), **(b)** using open CAD libs (mind ShareAlike on
*redistribution*), **(c)** treating Digi-Key/Mouser as live display/pricing feeds
only. For licensed redistributable data, **Nexar/Octopart is the one to negotiate**
— get ML-training + redistribution rights in writing.

---

## 4. State of the art on the hard sub-problems

### (a) LLM circuit/netlist synthesis
- **AnalogCoder** (arXiv 2405.14918): training-free agent, Python/SPICE w/ feedback;
  designed 20 circuits (+5 over GPT-4o). Limited to ≤~10 devices; a competing paper
  frames its valid-gen rate at ~57.3% (multi-token-per-line code errors). (High / Med)
- **LaMAGIC** (arXiv 2407.18269, ICML 2024): seq2seq topology gen, success **up to
  96% @ tolerance 0.01** (power-converter topologies). (High)
- **LaMAGIC2** (2506.10235): +34% success @ 0.01, ~10× lower MSE. (High)
- **SPICED** (2408.16018): LLM in-context bug/Trojan detection in SPICE netlists,
  no training. (High)
- **Masala-CHAI / Auto-SPICE** (2411.14299): automated schematic→SPICE pipeline +
  dataset. (High)
- **Failure modes:** incorrect/oversimplified logic, mishandled corner cases,
  Verilog-semantic violations, instruction-adherence hallucinations; Verilog
  syntactic correctness ~90% but functional drops up to 23.9% on non-English prompts.
  (High / Med)
- *"Artisan"* analog-LLM system: **name ambiguous/overloaded — unverified.**

### (b) PCB placement & routing (ML)
- **AlphaChip** (Google, Nature 2021): RL macro placement, claimed ≤6h, PPA ≥ human.
  **CONTESTED** — Cheng/Kahng "The False Dawn" (2306.09633, CACM 2024) found it did
  *not* beat simulated annealing / commercial placers on public benchmarks; Nature
  editor's note + addendum; Google rebuttal "That Chip Has Sailed" (2411.10053).
  **Scientifically unresolved as of 2026; no independent positive replication on
  public benchmarks.** (High that dispute exists / Med characterization)
- Most ML place-and-route targets **chips, not PCBs**; PCB-specific ML is thin
  (MIT MEng DRL thesis 2021; FanoutNet PPO claims 100% routability/+6.8% — secondary).
- **Freerouting** (GPLv3): de-facto open autorouter; known to leave unconnected
  tracks on dense boards. (High)
- **DeepPCB** (InstaDeep): commercial cloud RL autorouter (efficacy = vendor claims).

### (c) Reusable verification tooling (license-critical)
| Tool | License | Note |
|---|---|---|
| **ngspice** | **BSD** (permissive) | ✅ Safe to embed; mature SPICE engine |
| **PySpice** | **GPLv3** | Python→ngspice/Xyce; last stable v1.5 (2021), solo maintainer; has KiCadTools |
| **KiCad core + ERC** | **GPLv3+** | Programmatic ERC means driving KiCad/`kicad-cli` (copyleft) |
| **OpenSPICE** | — | Lighter pure-Python option, less mature |

**Load-bearing gap:** there is **no permissively-licensed standalone ERC/electrical-
rule engine.** A permissive seam/rule validator is something we'd build — and it's
defensible.

---

## 5. Market & moat

- **Where the money is:** EDA ~$14.5B (2025); IC tooling dominated by Synopsys/
  Cadence/Siemens (~75%). **PCB-design software is small (~$3–4B), fragmented**,
  no non-Big-3 vendor >5%. (High / Low-Med on the $4B figure — single source)
- **Willingness to pay:** KiCad/EasyEDA free anchor price to ~zero for hobbyists/
  startups; Flux $0–$158/mo; Altium ~$1,500–$4,500/seat/yr; Zuken/Cadence up to
  six figures. **Only conservative enterprise EE teams pay well — and they're the
  most AI-skeptical.** (High/Med)
- **Practitioner sentiment (earned skepticism):** three generations of autorouters
  overpromised; EEs reject "route the whole board for me" but *do* use interactive
  automation. Trust is the central GTM barrier; verification/physics-grounding is
  the lever. (Med — vendor blogs + HN, partially rate-limited)
- **Defensibility:** raw LLMs = **not** the moat (insiders concede). Defensible:
  proprietary physics/RL engines (Quilter), verified+manufacturable parts data
  (EasyEDA/JLC), enterprise workflow lock-in + managed libraries (Cadence/Altium),
  fab integration.
- **Verified-block-library thesis:** reuse *productivity* is proven; reuse as a
  *standalone business* has essentially **one venture-stage data point (CELUS
  CUBOs), quiet since 2022.** Inter-block connection is an open problem
  (TypedSchematics 2509.14576). **Highest-uncertainty leg of the thesis.** (Med/Low)
- **Manufacturing integration = the proven monetization:** JLCPCB/EasyEDA/LCSC are
  sister companies (design→parts→fab→assembly); EasyEDA is a **free funnel** into
  JLCPCB fab/assembly/parts margin (JLC online store ~$273M, 2025). One-click order,
  520k+ in-stock assembly parts. (High / Med on the $273M estimate)

---

## 6. The three biggest risks to the thesis

1. **The moat leg we lean on is the least commercially proven.** Verified-block-
   library-as-a-business = one quiet venture-stage example + an open research
   problem. De-risk this first.
2. **Monetization vise.** The segment that *wants* NL (makers/startups) won't pay;
   the segment that *pays* (enterprise EE) won't trust AI. The proven model is
   **manufacturing integration** (give tool away, monetize fab) — our "export to
   PCBWay" instinct may be the *business model*, not a feature.
3. **Data moat is expensive and partly boxed in.** Trustworthy parts data requires
   human review (~86% extraction ceiling), and the cheap shortcut (distributor APIs)
   is legally closed.

---

## Appendix: key primary sources

- Tools: github.com/atopile/atopile · github.com/tscircuit/tscircuit ·
  github.com/devbisme/skidl · jitx.com · phdl.sourceforge.net
- Startups: flux.ai/p/pricing · ycombinator.com/companies/diode-computers-inc ·
  celus.io · quilter.ai · cadence.com (Allegro X AI) · altium.com/newsroom · zuken.com
- Data: nexar.com/api · support.snapmagic.com · kicad.org/libraries/license ·
  developer.digikey.com/api-user-agreement · mouser.com/apiterms ·
  github.com/octopart/CPL-KiCad-Library · github.com/yaqwsx/jlcparts
- Research: arXiv 2405.14918, 2407.18269, 2506.10235, 2408.16018, 2411.14299,
  2502.16540, 2305.14874, 2412.05301, 2306.09633, 2411.10053, 2509.14576
- Verification: github.com/PySpice-org/PySpice · ngspice.sourceforge.io/devel.html ·
  kicad.org/about/licenses · github.com/freerouting/freerouting
- Market: precedenceresearch.com · sanieinstitute.substack.com · datagravity.dev ·
  pcbsync.com/altium-designer-price · jlcpcb.com · easyeda.com
