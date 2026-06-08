# Monetization & Business Model

> Pushing on **Risk #2 from [`DESIGN.md`](./DESIGN.md)** — the monetization vise.
> Grounded in the cited research in [`RESEARCH.md`](./RESEARCH.md) plus a focused
> second pass on fab partner economics and the supplier-pays model (2026-06-08).
>
> Confidence tags: **High / Med / Low** as in RESEARCH.md.

---

## 1. The vise (restated)

- The segment that **wants** NL-driven design (makers, hardware startups) has
  **near-zero willingness to pay** — KiCad/EasyEDA are free and Flux's free tier
  anchors price to ~$0. (High)
- The segment that **pays well** (enterprise EE teams, $2.5k–7.5k/seat/yr) is
  **conservative and AI-skeptical**, with incumbent lock-in (Altium/Cadence/Zuken).
  (High)
- The only **proven** low-end monetization is **manufacturing integration**
  (free tool → fab/assembly/parts margin, à la JLC/EasyEDA ~$273M). (High)

**The trap:** charging per-seat for an NL tool means competing with free, for the
customers least willing to pay. We need to break the "user = payer" assumption.

---

## 2. Two reframes the research unlocks

### Reframe A — **The payer is not always the user.**
The entire component-data layer already runs on this: **Octopart, SnapEDA/SnapMagic,
and Ultra Librarian are all free to engineers and paid by component manufacturers**
(CAD-model syndication + analytics + lead-gen), anchored on the multi-year
**"design win"** (a spec-in sustains 5–10 yrs of part revenue → manufacturers pay
to influence early design choices). (High) Our verified-block library *is* a
design-win surface — semis would pay to be the default block.
> Caveat: proven GTM but **modest standalone** (SnapEDA ~$1M rev; Octopart sold for
> $12M). It thrives *inside* a platform, not as a lone revenue engine. (Med)

### Reframe B — **Price the avoided respin, not the seat.**
A respin pain is real and quantified: **~2.9 respins/project × ~$44k each, ~4 weeks
delay per spin**, and **40–60% of issues originate in the schematic/footprint phase**
— exactly the error class our validator targets. (Med — mostly EDA-vendor sources +
one 2018 study) This lets us price on **value delivered (right-first-time)** rather
than compete on commoditized seat pricing. It's literally Quilter's model: "pay only
for approved designs." (High)

---

## 3. The five model options, scored against the evidence

| Model | Mechanism | Evidence | Verdict |
|---|---|---|---|
| **A. Per-seat SaaS** | Subscription/seat (Flux, Altium) | Flux's actual choice ($20–158/mo); the only *proven* independent path | **Viable but commoditized** — anchored to zero by free tools; not differentiated. Not the primary bet |
| **B. Fab referral** | Affiliate/coupon on fab orders | PCBWay = coupon-based ($10/$5); ~10% only on "Shared Projects"; JLC gated. Bare board → **cents–$3/order**; assembly → **$3–30/order** | **Secondary at best.** Flux deliberately did *not* make this primary. Money is only in *assembly* orders, not bare boards |
| **C. Fab API markup** | Pay fab via partner balance, bill customer, keep spread | PCBWay `ConfirmOrder` + JLC API technically support it; **wholesale margin undisclosed → must negotiate** | **Possible upside, unproven.** Validate whether real margin (vs. list-price reselling) exists |
| **D. Supplier-pays / design-win** | Semis pay for their verified blocks to be the default | Proven model (Octopart/SnapEDA/UL); design-win = 5–10yr revenue | **Best scalable engine that ignores user WTP** — but chicken-and-egg (needs designer volume first); modest until scale |
| **E. Outcome / correctness guarantee** | Pay per validated/approved design; "right-first-time" SLA | Quilter precedent; anchored on $44k × 2.9-spin respin pain | **Best alignment with our actual moat** (validation) — but needs the validation tech to be trustworthy + raises liability |

**No single model wins cleanly.** A/B compete with free; C/D/E depend on assets we
don't have *yet* (negotiated margin / designer volume / trustworthy validation).

---

## 4. Recommendation — a layered, sequenced model

**Don't bet the company on per-seat SaaS.** Build a stack where the LLM/tool is a
**loss-leader** and revenue comes from places foundation models *don't* commoditize:
**validated outcomes, fab order flow, and supplier design-wins.**

```
   Value-based core      ←  E. charge for VALIDATED designs / "right-first-time" tier
        +
   Fab integration       ←  C. order via API, capture ASSEMBLY-order economics
        +
   Supplier design-wins  ←  D. semis pay for default verified blocks (scale engine)
        ─────────────────
   (per-seat = optional convenience tier, never the primary bet)
```

### Sequencing (tied to technical de-risking)
- **Phase 0 — now:** prove the **vertical-slice validator works** (DESIGN.md §7).
  This is the precondition for *both* the guarantee model (E) *and* supplier trust (D).
- **Phase 1 — wedge revenue:** charge target startups on a **value basis** (per
  validated design or a correctness tier), and wire in **fab ordering** to capture
  **assembly-order** economics (B/C). Validates correctness-WTP *and* builds volume.
- **Phase 2 — scale engine:** once designer volume exists, turn on **supplier-pays
  design-wins** (D) and negotiate fab **wholesale margin** (C) + Nexar/Octopart data.
- **Phase 3 — up-market:** enterprise managed-library + guarantee SLAs once track
  record and trust exist.

### Avoid
- Betting the company on **per-seat SaaS** (commoditized, anchored to zero).
- Betting on **bare-board fab referral** (pennies/order).
- Going **enterprise-first** (slow, AI-skeptical, incumbent-locked) before trust exists.

---

## 5. What must be validated before committing (open unknowns)

1. **Does real fab wholesale margin exist?** PCBWay/JLC APIs allow ordering, but
   neither discloses a partner discount. → Negotiate directly; confirm spread > list.
   (Unverified/gated)
2. **Will the wedge customer pay for a "guarantee," or expect correctness for free?**
   → Customer discovery on respin economics vs. their actual budget. The $44k/2.9-spin
   stat is one 2018 study — validate against *their* numbers, not the average.
3. **Chicken-and-egg on supplier-pays:** need designer volume before semis pay. →
   Phase-1 volume is the gate; don't model D revenue early.
4. **Liability of a correctness "guarantee."** → Scope it (validation pass, not
   fitness-for-purpose) before making the promise.

---

## 6. One-paragraph bottom line

The NL tool is a **loss-leader**, not the product. Don't sell seats into a market
anchored at free. Sell **validated outcomes** (price the avoided respin), capture
**assembly-order** economics through fab APIs, and — once you have designer volume —
turn on the **supplier-pays design-win** engine that the entire component-data
industry already runs on. Every one of those revenue lines is defended by something
foundation models don't give away: trustworthy validation, manufacturing integration,
and a verified-block channel. The gating prerequisite for all three is the same
**vertical-slice validator** we need to build first anyway — so the technical and
business de-risking are the same first step.

> Updates Risk #2 in [`DESIGN.md`](./DESIGN.md). Evidence base in [`RESEARCH.md`](./RESEARCH.md).
