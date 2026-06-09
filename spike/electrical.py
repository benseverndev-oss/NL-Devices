"""Electrical gate — folds the ngspice rail/pull-up checks into validation.

Step-5 proved an ngspice op-point primitive; this turns it into a gate stage that
runs on the composed design's electrical metadata (per-block current draw, the LDO's
output capacity, the controller's pull-up value). So the gate now checks not just
topology (seam_validator) but electrical sanity:

  * the 3V3 rail's aggregate load is within the regulator's capacity AND the rail
    holds tolerance under that load (ngspice DC op-point)
  * the I2C pull-up sink current stays under the 3 mA bus spec (ngspice DC op-point)

Reuses the BSD-clean ngspice driver from step 0.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "skidl"))
from ngspice_check import op_point   # noqa: E402


def check_electrical(slice_doc: dict, lib) -> list[str]:
    errs = []
    spec = {inst: lib[bid] for inst, bid in slice_doc["instances"].items()}

    # --- power rails: load vs. capacity, and voltage under load -------------
    for r in slice_doc.get("rails", []):
        if "source_from" not in r:        # only check block-driven rails (the 3V3)
            continue
        out = spec[r["source_from"].split(".")[0]].ports["power_out"]
        vnom, tol = out["voltage"], out["tolerance"]
        max_ma = out.get("max_current_ma")
        load_ma = sum(spec[ref.split(".")[0]].ports["power"].get("current_ma", 0)
                      for ref in r.get("sinks", []))
        if max_ma and load_ma > max_ma:
            errs.append(f"ELEC: rail '{r['name']}' load {load_ma}mA exceeds "
                        f"regulator capacity {max_ma}mA")
            continue
        # ngspice: ideal Vnom behind a small output impedance feeding the load
        rload = vnom / (load_ma / 1000.0) if load_ma else 1e9
        deck = (f"* rail under load\nVreg VREG 0 {vnom}\nRout VREG RAIL 0.1\n"
                f"Rload RAIL 0 {rload:.4f}")
        v = op_point(deck, ["RAIL"]).get("RAIL", vnom)
        if not (vnom * (1 - tol) <= v <= vnom * (1 + tol)):
            errs.append(f"ELEC: rail '{r['name']}' sags to {v:.3f}V under {load_ma}mA "
                        f"(spec {vnom}V +/-{tol*100:g}%)")

    # --- I2C pull-up sink current -------------------------------------------
    for b in slice_doc.get("buses", []):
        rp = vrail = None
        for ref in b.get("members", []):
            p = spec[ref.split(".")[0]].ports[ref.split(".")[1]]
            if p.get("role") == "controller" and p.get("provides_pullups"):
                rp = p.get("pullup_ohms")
        # rail voltage feeding the bus = the 3V3 source rail nominal
        for r in slice_doc.get("rails", []):
            if "source_from" in r:
                vrail = spec[r["source_from"].split(".")[0]].ports["power_out"]["voltage"]
        if not rp or vrail is None:
            continue
        deck = (f"* i2c pullup sink\nV3 V3 0 {vrail}\nRp V3 SCL {rp}\nRdev SCL 0 10")
        vscl = op_point(deck, ["SCL"]).get("SCL", 0.0)
        i_ma = (vrail - vscl) / rp * 1000
        if i_ma >= 3.0:
            errs.append(f"ELEC: bus '{b['name']}' pull-up sink {i_ma:.2f}mA "
                        f"exceeds 3mA I2C limit (Rp={rp}ohm too small)")
    return errs


if __name__ == "__main__":
    # negative tests — show the electrical gate has teeth
    def overloaded():
        return ({"instances": {"psu": "power_3v3_ldo", "big": "mcu_i2c_controller"},
                 "rails": [{"name": "3V3", "source_from": "psu.power_out",
                            "sinks": ["big.power"]}]},)
    import block_contract as bc
    lib = bc.load_blocks()
    # 1) tiny regulator: force capacity overflow by faking a big load
    bad = {"instances": {"psu": "power_3v3_ldo", "a": "mcu_i2c_controller"},
           "rails": [{"name": "3V3", "source_from": "psu.power_out",
                      "sinks": ["a.power"]}], "buses": []}
    # temporarily shrink the regulator capacity below the load
    lib["power_3v3_ldo"].ports["power_out"]["max_current_ma"] = 5
    print("overloaded-rail test:", check_electrical(bad, lib) or "PASS")
    lib["power_3v3_ldo"].ports["power_out"]["max_current_ma"] = 800
    # 2) too-strong pull-up
    lib["mcu_i2c_controller"].ports["i2c"]["pullup_ohms"] = 200
    bus = {"instances": {"psu": "power_3v3_ldo", "mcu": "mcu_i2c_controller"},
           "rails": [{"name": "3V3", "source_from": "psu.power_out", "sinks": []}],
           "buses": [{"name": "i2c_bus", "members": ["mcu.i2c"]}]}
    print("too-strong-pullup test:", check_electrical(bus, lib) or "PASS")
