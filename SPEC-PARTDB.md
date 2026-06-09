# Spec — Ground-Truth Part-Data Layer

> Closes the top 🔴 of [`GAPS.md`](./GAPS.md) §4d / §5 item 3: *"the ground-truth
> part DB does not exist — validation runs against hand-typed YAML; a typo in a
> block's numbers is undetectable."* This is the **trust layer** the DESIGN
> architecture diagram names but the spike never built.

## Problem

Every verified block hand-types its identity and electrical numbers:

```yaml
bound_part: {lcsc: C6186, mpn: AMS1117-3.3, footprint: SOT-223-3}
ports:
  power_out: {role: source, voltage: 3.3, max_current_ma: 800}
```

Nothing checked any of it. A fat-fingered LCSC code, a wrong MPN, a 3.3V block
accidentally bound to the 5V regulator, or a supply voltage outside the part's
rating all validated **clean** — because there was no ground truth to check against.
The product's whole claim is *"validated against a ground-truth component database."*
Without the database, that claim was unbacked.

## Design — two layers, split by trust model

```
  ┌─ ingest (networked, occasional, brittle-by-nature) ────────────────────┐
  │  EasyEDA components API  ─► identity, exact KiCad package, stock        │
  │  LCSC __NEXT_DATA__       ─► parametric electrical attributes           │
  │            └────────────► normalize ─► parts_snapshot.json (committed)  │
  └────────────────────────────────────────────────────────────────────────┘
                                     │  the pinned snapshot is the only artifact
                                     ▼  CI ever reads — network is never on its path
  ┌─ verify (offline, deterministic, runs in CI) ──────────────────────────┐
  │  block_contract.load_blocks() ─► each bound_part + ports                │
  │            vs parts_snapshot.json ─► per-field VERIFIED / MISMATCH /    │
  │            MISSING / UNVERIFIABLE / WARN ─► exit 1 on any hard fail      │
  └────────────────────────────────────────────────────────────────────────┘
```

The split is the point: **ingest is allowed to be flaky** (it scrapes web sources and
only ever *writes* the snapshot); **verify is reproducible** (it reads the committed
snapshot, so CI is offline and deterministic). Refreshing ground truth is a
deliberate, reviewable diff to `parts_snapshot.json`, not a live dependency.

## What is actually ground-truthed (be honest)

The verifier reports every field as one of five states and **never claims more than it
checked** — directly answering the GAPS critique that the project's "done" claims ran
ahead of the code.

| State | Meaning | Fails CI? |
|---|---|:--:|
| `VERIFIED` | checked against ground truth, agrees | — |
| `MISMATCH` | checked, **disagrees** | ✅ |
| `MISSING` | part absent from the snapshot | ✅ |
| `UNVERIFIABLE` | no ground-truth field exists yet (flagged, not blessed) | — |
| `WARN` | soft signal (manufacturer naming, low stock) | — |

**Verifiable today** (28 fields across the 4 blocks, all green):
- LCSC code resolves to a real part
- MPN (exact, normalized)
- manufacturer (alias-matched: `ST`↔`STMicroelectronics`, `TI`↔`Texas Instruments`, …)
- footprint family (`SOIC-8` ⊆ `SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL`)
- in-stock / orderable
- **fixed output voltage** of a regulator block (`power_out 3.3V == part 3.3V`)
- **operating-voltage range** for every sink (`3.3V ∈ [2.0–3.6V]` for the STM32)
- **output-current capacity** (`max_current_ma 800 ≤ part 1000mA`)
- bus interface (`I2C` present on the peripheral's real part)

**Not yet ground-truthed** (explicitly `UNVERIFIABLE`, stays trusted YAML):
- I2C `address_base` (datasheet-level, not an LCSC parametric attribute)
- voltage `tolerance` values, pin-level data

## Files

| File | Role |
|---|---|
| `spike/partdb.py` | library + **ingest** CLI; EasyEDA/LCSC fetch + attribute normalization; snapshot IO; the normalization helpers the verifier reuses |
| `spike/verify_parts.py` | **offline gate** (CI): every block vs snapshot, honest per-field report; `--selftest` injects part-data faults |
| `spike/parts_snapshot.json` | pinned ground truth (4 parts), full provenance: parsed attrs + raw source values + URLs + fetch date |

`requests` is an **ingest-only** dependency — not in `spike/requirements.txt`, never
imported on the CI/verify path.

## Verification (run, not asserted)

```
python3 verify_parts.py            → PASS  28 verified · 0 mismatch · 2 unverifiable
python3 verify_parts.py --selftest → PASS  6/6 injected faults caught
```

The self-test mirrors `block_contract.py --faults`: it perturbs real blocks and
proves the gate fires on the exact threat model — **bad part data**: bogus LCSC code,
wrong MPN, wrong footprint, an LDO bound to the wrong-voltage part, an over-claimed
current rating, and a supply outside the part's rated range. This is evidence the
trust layer works, not just that it exists.

CI runs both as a new step in [`.github/workflows/ci.yml`](./.github/workflows/ci.yml).

## What this unlocks / what is next (updates GAPS §5)

- ✅ **The "ground-truth database" noun now exists** for identity + the most
  load-bearing electrical numbers, with provenance and an offline CI gate.
- ⏭️ **Breadth:** `ingest --from-blocks` scales to every new block automatically;
  each new part is one networked fetch + a committed snapshot diff.
- ⏭️ **Depth:** add `address_base` / tolerance ground truth (needs a datasheet- or
  registry-level source — ties into the datasheet-extraction pipeline of GAPS §4b).
- ⏭️ **Reproducibility:** the snapshot also removes part-pick network flakiness for
  *validation*; a future step can pin the atopile build's LCSC pick to it too.
