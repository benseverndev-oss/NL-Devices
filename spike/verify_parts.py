"""Offline part-data gate — check every verified block's `bound_part` and declared
electrical numbers against the pinned ground-truth snapshot (`parts_snapshot.json`).

This is the trust layer GAPS.md §4d said was missing: until now a wrong LCSC code,
MPN, footprint, or supply voltage in a block's YAML was *trusted blindly*. Now it is
*checked* against sourced data — deterministically, with no network (CI-safe).

The report is deliberately honest about coverage. Every field is one of:
  VERIFIED      — checked against ground truth and agrees
  MISMATCH      — checked and DISAGREES            → hard fail (exit 1)
  MISSING       — part not in the snapshot at all   → hard fail (exit 1)
  UNVERIFIABLE  — no ground-truth field exists yet (e.g. I2C address_base,
                  tolerances) → still trusted YAML, but flagged, never silently blessed
  WARN          — soft signal (manufacturer naming, low stock) → does not fail

Run:
  python3 verify_parts.py             # gate every block against the snapshot
  python3 verify_parts.py --selftest  # inject part-data faults; prove the gate fires
"""
from __future__ import annotations

import copy
import sys
from dataclasses import dataclass

import block_contract
import partdb

VERIFIED, MISMATCH, MISSING, UNVERIFIABLE, WARN = (
    "VERIFIED", "MISMATCH", "MISSING", "UNVERIFIABLE", "WARN")
_HARD_FAIL = {MISMATCH, MISSING}


@dataclass
class Finding:
    field: str
    status: str
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.status in _HARD_FAIL


def _f(field, status, detail=""):
    return Finding(field, status, detail)


# ---- the checks --------------------------------------------------------------
def verify_block(block, snapshot: dict[str, partdb.PartRecord]) -> list[Finding]:
    """Pure: all findings for one block. No I/O, so the self-test can feed it
    mutated copies."""
    bp = block.bound_part or {}
    lcsc = bp.get("lcsc")
    if not lcsc:
        return [_f("bound_part", UNVERIFIABLE, "abstract block, no bound part")]

    gt = snapshot.get(lcsc)
    if gt is None:
        return [_f("lcsc", MISSING,
                   f"{lcsc} absent from snapshot — run `python3 partdb.py ingest --from-blocks`")]

    out = [_f("lcsc", VERIFIED, f"{lcsc} present in ground-truth snapshot")]

    # identity
    if partdb.norm_mpn(bp.get("mpn")) == partdb.norm_mpn(gt.mpn):
        out.append(_f("mpn", VERIFIED, f"{gt.mpn}"))
    else:
        out.append(_f("mpn", MISMATCH, f"block={bp.get('mpn')!r} ground-truth={gt.mpn!r}"))

    if partdb.manufacturer_matches(bp.get("manufacturer"), gt.manufacturer):
        out.append(_f("manufacturer", VERIFIED, f"{gt.manufacturer}"))
    else:
        out.append(_f("manufacturer", WARN,
                      f"block={bp.get('manufacturer')!r} ground-truth={gt.manufacturer!r} (naming differs)"))

    if partdb.footprint_matches(bp.get("footprint"), gt.package):
        out.append(_f("footprint", VERIFIED, f"{bp.get('footprint')} ⊆ {gt.package}"))
    else:
        out.append(_f("footprint", MISMATCH,
                      f"block={bp.get('footprint')!r} ground-truth package={gt.package!r}"))

    # manufacturability
    if gt.stock is None:
        out.append(_f("stock", UNVERIFIABLE, "no stock figure in snapshot"))
    elif gt.stock > 0:
        out.append(_f("stock", VERIFIED, f"{gt.stock} in stock at LCSC"))
    else:
        out.append(_f("stock", WARN, "0 in stock — not currently orderable"))

    out.extend(_verify_electrical(block, gt))
    return out


def _verify_electrical(block, gt: partdb.PartRecord) -> list[Finding]:
    out: list[Finding] = []
    attrs = gt.attributes or {}
    for pname, p in (block.ports or {}).items():
        ptype, role = p.get("type"), p.get("role")

        if ptype == "power" and role == "sink" and "voltage" in p:
            op = attrs.get("operating_voltage_v")
            if op and op.get("max") is not None:
                lo = op.get("min") or 0.0
                hi = op["max"]
                if lo <= p["voltage"] <= hi:
                    out.append(_f(f"{pname}.voltage", VERIFIED,
                                  f"{p['voltage']}V within part rating [{lo}–{hi}V] ({op['raw']})"))
                else:
                    out.append(_f(f"{pname}.voltage", MISMATCH,
                                  f"{p['voltage']}V outside part rating [{lo}–{hi}V] ({op['raw']})"))
            else:
                out.append(_f(f"{pname}.voltage", UNVERIFIABLE, "no operating-voltage rating in snapshot"))

        if ptype == "power" and role == "source" and "voltage" in p:
            ov = attrs.get("output_voltage_v")
            if ov and ov.get("value") is not None:
                if abs(p["voltage"] - ov["value"]) <= 0.05:
                    out.append(_f(f"{pname}.voltage", VERIFIED,
                                  f"{p['voltage']}V == part fixed output {ov['value']}V"))
                else:
                    out.append(_f(f"{pname}.voltage", MISMATCH,
                                  f"block claims {p['voltage']}V but part outputs {ov['value']}V ({ov['raw']})"))
            else:
                out.append(_f(f"{pname}.voltage", UNVERIFIABLE, "no fixed-output-voltage rating in snapshot"))

            if "max_current_ma" in p:
                oc = attrs.get("output_current_ma")
                if oc and oc.get("value_ma") is not None:
                    if p["max_current_ma"] <= oc["value_ma"] + 1e-6:
                        out.append(_f(f"{pname}.max_current_ma", VERIFIED,
                                      f"{p['max_current_ma']}mA ≤ part capacity {oc['value_ma']:.0f}mA ({oc['raw']})"))
                    else:
                        out.append(_f(f"{pname}.max_current_ma", MISMATCH,
                                      f"block claims {p['max_current_ma']}mA > part capacity "
                                      f"{oc['value_ma']:.0f}mA ({oc['raw']})"))
                else:
                    out.append(_f(f"{pname}.max_current_ma", UNVERIFIABLE, "no output-current rating in snapshot"))

        if ptype == "i2c":
            if role == "peripheral":
                iface = attrs.get("interface")
                if iface:
                    if any(x.upper().replace("-", "") in ("I2C", "IIC") for x in iface):
                        out.append(_f(f"{pname}.interface", VERIFIED, f"part interface {iface} includes I2C"))
                    else:
                        out.append(_f(f"{pname}.interface", MISMATCH, f"part interface {iface} is not I2C"))
                else:
                    out.append(_f(f"{pname}.interface", UNVERIFIABLE, "no interface attribute in snapshot"))
                if "address_base" in p:
                    out.append(_f(f"{pname}.address_base", UNVERIFIABLE,
                                  f"0x{p['address_base']:02X} is datasheet-level — no ground-truth field yet"))
    return out


# ---- reporting ---------------------------------------------------------------
_GLYPH = {VERIFIED: "✓", MISMATCH: "✗", MISSING: "✗", UNVERIFIABLE: "·", WARN: "!"}


def report(blocks, snapshot) -> bool:
    concrete = {bid: b for bid, b in blocks.items() if (b.bound_part or {}).get("lcsc")}
    print(f"Ground-truth part-data gate — {len(concrete)} bound blocks vs "
          f"{len(snapshot)}-part snapshot\n" + "=" * 72)
    tally = {k: 0 for k in (VERIFIED, MISMATCH, MISSING, UNVERIFIABLE, WARN)}
    any_fail = False
    for bid, b in sorted(concrete.items()):
        findings = verify_block(b, snapshot)
        block_fail = any(f.failed for f in findings)
        any_fail |= block_fail
        print(f"\n{'FAIL' if block_fail else 'OK  '}  {bid}  "
              f"({b.bound_part.get('lcsc')} · {b.bound_part.get('mpn')})")
        for f in findings:
            tally[f.status] += 1
            print(f"    {_GLYPH[f.status]} {f.status:<12} {f.field:<22} {f.detail}")
    print("\n" + "=" * 72)
    print(f"summary: {tally[VERIFIED]} verified · {tally[MISMATCH]} mismatch · "
          f"{tally[MISSING]} missing · {tally[UNVERIFIABLE]} unverifiable · {tally[WARN]} warn")
    print("note: UNVERIFIABLE fields (I2C address_base, tolerances) are trusted YAML "
          "with no ground-truth source yet — flagged, not blessed.")
    print("RESULT:", "FAIL — block data disagrees with ground truth" if any_fail
          else "PASS — all bound parts agree with ground truth")
    return not any_fail


# ---- self-test: prove the gate catches part-data faults ----------------------
def _mutate(block, **path_values):
    """deepcopy a block and apply 'a.b'->value edits to bound_part / ports."""
    b = copy.deepcopy(block)
    for dotted, value in path_values.items():
        head, _, tail = dotted.partition(".")
        if head == "bound_part":
            b.bound_part[tail] = value
        elif head == "port":
            pname, _, key = tail.partition(".")
            b.ports[pname][key] = value
    return b


def selftest(blocks, snapshot) -> bool:
    ldo, mcu = blocks["power_3v3_ldo"], blocks["mcu_i2c_controller"]
    cases = [
        ("bogus LCSC code",        _mutate(ldo, **{"bound_part.lcsc": "C0000000"}), "lcsc", MISSING),
        ("wrong MPN",              _mutate(ldo, **{"bound_part.mpn": "AMS1117-5.0"}), "mpn", MISMATCH),
        ("wrong footprint",        _mutate(ldo, **{"bound_part.footprint": "SOIC-8"}), "footprint", MISMATCH),
        ("LDO wrong output volts", _mutate(ldo, **{"port.power_out.voltage": 5.0}), "power_out.voltage", MISMATCH),
        ("LDO over-claims current",_mutate(ldo, **{"port.power_out.max_current_ma": 5000}), "power_out.max_current_ma", MISMATCH),
        ("MCU supply out of range",_mutate(mcu, **{"port.power.voltage": 12.0}), "power.voltage", MISMATCH),
    ]
    print("self-test — each injected part-data fault must be caught:\n" + "-" * 72)
    all_ok = True
    for label, block, field, expect in cases:
        findings = verify_block(block, snapshot)
        hit = next((f for f in findings if f.field == field and f.status == expect), None)
        ok = hit is not None
        all_ok &= ok
        print(f"  [{'caught' if ok else 'MISSED'}] {label:<26} "
              f"expect {expect} on {field}")
        if hit:
            print(f"        └─ {hit.detail}")
    # and the unmodified blocks must all pass clean
    clean = all(not any(f.failed for f in verify_block(b, snapshot))
                for b in blocks.values() if (b.bound_part or {}).get("lcsc"))
    all_ok &= clean
    print(f"  [{'ok' if clean else 'FAIL'}] real blocks all pass against ground truth")
    print("-" * 72)
    print("SELFTEST:", "PASS" if all_ok else "FAIL")
    return all_ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    blocks = block_contract.load_blocks()
    snapshot = partdb.load_snapshot()
    if not snapshot:
        print("no parts_snapshot.json found — run `python3 partdb.py ingest --from-blocks` first",
              file=sys.stderr)
        raise SystemExit(2)
    if "--selftest" in sys.argv:
        ok = selftest(blocks, snapshot)
    else:
        ok = report(blocks, snapshot)
    raise SystemExit(0 if ok else 1)
