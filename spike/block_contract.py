"""Verified-block contract loader — wires authored YAML blocks into the validator.

This formalizes the SPIKE.md §3 block contract and closes the loop: the seam
checks now read their inputs from authored `blocks/*.yaml` + a `slices/*.yaml`
composition, instead of hand-built Python. The semantic metadata atopile cannot
infer (I2C address, supply range) lives here, in the block contract — exactly the
gap the spike surfaced.

It reuses the validation engine proven in `seam_validator.py`.

Run:  python3 block_contract.py            # validates slices/sensor_node.yaml
      python3 block_contract.py --faults   # also injects the 3 seam faults
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import seam_validator as sv

HERE = Path(__file__).parent


# ---- schema -----------------------------------------------------------------
@dataclass
class BlockSpec:
    id: str
    version: str
    function: str
    ports: dict
    bound_part: dict | None = None
    invariants: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    def port(self, name: str) -> dict:
        if name not in self.ports:
            raise KeyError(f"block '{self.id}' has no port '{name}'")
        return self.ports[name]


def _validate_spec(d: dict, src: str) -> None:
    """Enforce the block-contract schema — fail loudly on a malformed block."""
    for k in ("id", "version", "function", "ports"):
        if k not in d:
            raise ValueError(f"{src}: missing required field '{k}'")
    for pname, p in d["ports"].items():
        t = p.get("type")
        if t not in ("power", "i2c"):
            raise ValueError(f"{src}: port '{pname}' has unknown type {t!r}")
        if t == "power":
            for k in ("role", "voltage", "tolerance"):
                if k not in p:
                    raise ValueError(f"{src}: power port '{pname}' missing '{k}'")
            if p["role"] not in ("source", "sink"):
                raise ValueError(f"{src}: power port '{pname}' bad role {p['role']!r}")
        else:  # i2c
            if p.get("role") not in ("controller", "peripheral"):
                raise ValueError(f"{src}: i2c port '{pname}' bad role {p.get('role')!r}")
            if p["role"] == "peripheral" and "address" not in p:
                raise ValueError(f"{src}: i2c peripheral '{pname}' missing 'address' "
                                 f"(required — atopile cannot infer it)")


def load_blocks(blocks_dir: Path = HERE / "blocks") -> dict[str, BlockSpec]:
    out = {}
    for f in sorted(blocks_dir.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        _validate_spec(d, f.name)
        out[d["id"]] = BlockSpec(
            id=d["id"], version=d["version"], function=d["function"],
            ports=d["ports"], bound_part=d.get("bound_part"),
            invariants=d.get("invariants", []), tags=d.get("tags", []))
    return out


# ---- compose: authored blocks + slice -> a validator Design -----------------
def build_design(slice_doc: dict, blocks: dict[str, BlockSpec]) -> sv.Design:
    insts = slice_doc["instances"]                       # inst -> block id

    def resolve(ref: str) -> tuple[str, dict]:           # "inst.port" -> (inst, port-spec)
        inst, port = ref.split(".")
        return inst, blocks[insts[inst]].port(port)

    rails = []
    for r in slice_doc.get("rails", []):
        if "source" in r:
            sv_v, sv_tol = r["source"]["voltage"], r["source"]["tolerance"]
        else:                                            # rail driven by a block source port
            _, sp = resolve(r["source_from"])
            sv_v, sv_tol = sp["voltage"], sp["tolerance"]
        sinks = []
        for ref in r.get("sinks", []):
            inst, sp = resolve(ref)
            sinks.append((inst, sp["voltage"], sp["tolerance"]))
        rails.append(sv.PowerRail(r["name"], sv_v, sv_tol, sinks=sinks))

    buses = []
    for b in slice_doc.get("buses", []):
        nodes = []
        for ref in b.get("members", []):
            inst, sp = resolve(ref)
            nodes.append(sv.I2CNode(block=inst, role=sp["role"],
                                    provides_pullups=sp.get("provides_pullups", False),
                                    address=sp.get("address")))
        buses.append(sv.I2CBus(b["name"], nodes=nodes))

    return sv.Design(slice_doc["name"], rails=rails, buses=buses)


def load_slice(path: Path, blocks: dict[str, BlockSpec]) -> sv.Design:
    return build_design(yaml.safe_load(path.read_text()), blocks)


# ---- report -----------------------------------------------------------------
def report(design: sv.Design) -> bool:
    res = sv.validate(design)
    failing = {k: v for k, v in res.items() if v}
    print(f"  [{'FAIL' if failing else 'PASS'}] {design.name}")
    for msgs in res.values():
        for m in msgs:
            print(f"       └─ {m}")
    return not failing


def inject_faults(design: sv.Design) -> list[tuple[str, sv.Design, str]]:
    """Perturb the contract-derived design to prove the checks still fire."""
    import copy
    out = []
    # 1. power-domain: move the MCU onto the 5V rail
    d = copy.deepcopy(design)
    rail5 = next(r for r in d.rails if r.name == "5V")
    rail3 = next(r for r in d.rails if r.name == "3V3")
    mcu = next(s for s in rail3.sinks if s[0] == "mcu")
    rail3.sinks.remove(mcu); rail5.sinks.append(mcu)
    out.append(("fault: MCU on 5V rail", d, "power-domain"))
    # 2. pull-ups: no participant provides them
    d = copy.deepcopy(design)
    for n in d.buses[0].nodes:
        n.provides_pullups = False
    out.append(("fault: no I2C pull-ups", d, "i2c-pullups"))
    # 3. address collision: a second peripheral at the same address
    d = copy.deepcopy(design)
    d.buses[0].nodes.append(sv.I2CNode("sensor_b", "peripheral", address=0x50))
    out.append(("fault: duplicate I2C address", d, "i2c-address"))
    return out


if __name__ == "__main__":
    blocks = load_blocks()
    print(f"loaded {len(blocks)} verified blocks: {', '.join(blocks)}")
    for b in blocks.values():
        part = b.bound_part["lcsc"] if b.bound_part else "—(abstract)"
        print(f"  · {b.id:<24} part={part}")
    print()

    design = load_slice(HERE / "slices" / "sensor_node.yaml", blocks)
    print("validating authored slice:")
    ok = report(design)

    all_ok = ok
    if "--faults" in sys.argv:
        print("\ninjecting seam faults (each must be caught):")
        for label, fd, expect in inject_faults(design):
            res = sv.validate(fd)
            failing = [k for k, v in res.items() if v]
            caught = failing == [expect]
            all_ok &= caught
            print(f"  [{'caught' if caught else 'MISSED'}] {label}")
            for msgs in res.values():
                for m in msgs:
                    print(f"       └─ {m}")

    print("\nRESULT:", "PASS" if all_ok else "FAIL")
    raise SystemExit(0 if all_ok else 1)
