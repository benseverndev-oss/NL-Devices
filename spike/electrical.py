"""Electrical gate — honest **analytic** limits on the composed design.

GAPS.md §3 / §5 item 6 called out the old version: it built ngspice decks that were an
ideal source behind a 0.1Ω resistor and a resistor divider — Ohm's law in a SPICE
costume, where the real pass/fail was the arithmetic next to the sim. That theatre is
gone. This module now does one thing and names it honestly: an **analytic** LDO
dropout-margin check on the gate path (fast, deterministic, no simulator).

The genuine transient simulations (I2C RC rise time, rail droop under a load step)
live in `spice_sim.py`, where a real ngspice `.tran` either validates these analytic
limits or stands on its own — see `SPEC-SPICE.md` and `spice_sim.py --selftest`.
Current-budget and the analytic I2C rise-time limit are enforced by `seam_validator`.

Interface unchanged: `check_electrical(slice_doc, lib) -> list[str]` (used by the
orchestrator gate).
"""
from __future__ import annotations


def check_electrical(slice_doc: dict, lib) -> list[str]:
    """Analytic electrical limits the topology checks don't cover. Today: LDO dropout —
    a linear regulator needs Vin ≥ Vout + Vdropout or it falls out of regulation. Only
    runs where the source block declares `dropout_v` (else there's no datum to check)."""
    errs: list[str] = []
    spec = {inst: lib[bid] for inst, bid in slice_doc["instances"].items()}

    for r in slice_doc.get("rails", []):
        if "source_from" not in r:            # only block-driven rails have a regulator
            continue
        src = r["source_from"].split(".")[0]
        out = spec[src].ports.get("power_out", {})
        vin_port = spec[src].ports.get("power_in", {})
        vout, vin, drop = out.get("voltage"), vin_port.get("voltage"), out.get("dropout_v")
        if vout is None or vin is None or drop is None:
            continue                          # no dropout spec -> analytic check not applicable
        margin = vin - vout
        if margin < drop:
            errs.append(
                f"ELEC(analytic): LDO '{src}' dropout — Vin {vin}V - Vout {vout}V = "
                f"{margin:.2f}V is below the {drop}V dropout (regulator drops out of "
                f"regulation on rail '{r['name']}')")
    return errs


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import block_contract as bc
    lib = bc.load_blocks()

    good = {"instances": {"psu": "power_3v3_ldo"},
            "rails": [{"name": "3V3", "source_from": "psu.power_out", "sinks": []}],
            "buses": []}
    print("nominal 5V->3V3 dropout margin:", check_electrical(good, lib) or "PASS")

    # negative test: starve the LDO input below Vout + dropout
    lib["power_3v3_ldo"].ports["power_in"]["voltage"] = 3.6   # 3.6 - 3.3 = 0.3V < 1.3V dropout
    errs = check_electrical(good, lib)
    print("starved-input dropout test:", "caught" if errs else "MISSED")
    for e in errs:
        print(f"   └─ {e}")
    raise SystemExit(0 if errs else 1)
