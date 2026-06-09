# Ground-Truth Part DB

The "validated against a ground-truth database" half of the thesis: a sourced, pinned
component snapshot + an offline gate that catches a wrong LCSC code / MPN / footprint /
supply voltage in a block's YAML.

## Pieces (`spike/`)
- `partdb.py` + `parts_snapshot.json` — ingest sourced data per LCSC part into a pinned
  snapshot **with provenance**. Working sources from the sandbox: EasyEDA components API
  (`easyeda.com/api/products/{C-code}/components`, needs `Referer`/`Origin: easyeda.com`
  headers or 403) for identity + exact package + stock; LCSC `__NEXT_DATA__` for
  parametric attrs.
- `verify_parts.py` — **offline CI gate**: every block's `bound_part` + declared
  electricals checked against the snapshot. `--selftest` proves it catches a bogus LCSC
  code, wrong MPN/footprint, an LDO bound to the wrong-voltage part, an over-claimed
  current, and a supply outside the part's rating.

## Status
28 fields VERIFIED / 0 mismatch across the bound blocks. The validator's `part-rail-rating`
check reads this snapshot ([seam-validator.md](seam-validator.md)), and the routed fab
package reconciles its bound ICs to it ([autoroute-pipeline.md](autoroute-pipeline.md)).

**Still open:** I2C `address_base` + tolerances have no source yet (reported `UNVERIFIABLE`,
not blessed); the snapshot does **not** pin the `ato build` LCSC part-pick (so passives
the build picks are reported, not blessed); no price feed.

## Source of truth / specs
[`SPEC-PARTDB.md`](../../SPEC-PARTDB.md), [`GAPS.md`](../../GAPS.md) §4d.

---
**Classification:** architecture/active • **Last updated:** 2026-06-09
