"""Prototype of the NL-Devices seam-validator — the moat artifact.

Step-3 finding: atopile's typed model + constraint solver catches the power-domain
mismatch (Fault 1) for FREE, but does NOT enforce I2C topology rules — missing
pull-ups (Fault 2) and address collisions (Fault 3) both build clean. So the
seam-validation layer is something we own. This module shows it is small,
deterministic, and substrate-independent: it runs over a typed block-graph (our
"verified block" contract from SPIKE.md §3), not over any one EDA tool's internals.

It checks the three SPIKE.md §4 seams:
  1. power-domain compatibility   (the rail's voltage must lie within each sink's range)
  2. I2C pull-ups present          (some participant must pull SCL/SDA up)
  3. I2C address uniqueness        (no two peripherals share an address)

Run:  python3 seam_validator.py
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ---- typed design model (a tiny slice of the "verified block" contract) ------
@dataclass
class PowerRail:
    name: str
    source_v: float          # nominal volts the source provides
    source_tol: float        # fractional tolerance, e.g. 0.05
    sinks: list[tuple[str, float, float]] = field(default_factory=list)  # (block, req_v, tol)


@dataclass
class I2CNode:
    block: str
    role: str                # 'controller' | 'peripheral'
    provides_pullups: bool = False
    address: int | None = None   # 7-bit address (assigned from the range below)
    addr_base: int | None = None # lowest strappable address
    addr_bits: int = 0           # number of address pins -> range = 2**addr_bits


@dataclass
class I2CBus:
    name: str
    nodes: list[I2CNode] = field(default_factory=list)


@dataclass
class Design:
    name: str
    rails: list[PowerRail] = field(default_factory=list)
    buses: list[I2CBus] = field(default_factory=list)


def _interval(v: float, tol: float) -> tuple[float, float]:
    return (v * (1 - tol), v * (1 + tol))


# ---- the three seam checks ---------------------------------------------------
def check_power_domains(d: Design) -> list[str]:
    errs = []
    for r in d.rails:
        s_lo, s_hi = _interval(r.source_v, r.source_tol)
        for block, req_v, tol in r.sinks:
            k_lo, k_hi = _interval(req_v, tol)
            if not (k_lo <= s_lo and s_hi <= k_hi):   # source must fit inside sink range
                errs.append(
                    f"POWER: rail '{r.name}' = [{s_lo:.3f}V,{s_hi:.3f}V] is outside "
                    f"'{block}' accepted [{k_lo:.3f}V,{k_hi:.3f}V]")
    return errs


def check_i2c_pullups(d: Design) -> list[str]:
    errs = []
    for b in d.buses:
        if not any(n.provides_pullups for n in b.nodes):
            errs.append(f"I2C: bus '{b.name}' has no pull-up provider (SCL/SDA float)")
    return errs


def assign_addresses(d: Design) -> None:
    """Assign each peripheral a distinct address from its strappable range.
    Leaves address=None if the bus has run out of space (caught by the check)."""
    for b in d.buses:
        used = {n.address for n in b.nodes if n.address is not None}
        for n in b.nodes:
            if n.role != 'peripheral' or n.addr_base is None or n.address is not None:
                continue
            for a in range(n.addr_base, n.addr_base + (1 << n.addr_bits)):
                if a not in used:
                    n.address = a
                    used.add(a)
                    break


def check_i2c_addresses(d: Design) -> list[str]:
    errs = []
    for b in d.buses:
        seen: dict[int, str] = {}
        for n in b.nodes:
            if n.role != 'peripheral':
                continue
            if n.address is None:        # range exhausted during assignment
                errs.append(f"I2C: bus '{b.name}' address space exhausted for "
                            f"'{n.block}' (range 0x{n.addr_base:02X}.."
                            f"0x{n.addr_base + (1 << n.addr_bits) - 1:02X} full)")
                continue
            if n.address in seen:
                errs.append(
                    f"I2C: bus '{b.name}' address 0x{n.address:02X} collision "
                    f"('{seen[n.address]}' and '{n.block}')")
            seen[n.address] = n.block
    return errs


CHECKS = [("power-domain", check_power_domains),
          ("i2c-pullups", check_i2c_pullups),
          ("i2c-address", check_i2c_addresses)]


def validate(d: Design) -> dict[str, list[str]]:
    return {name: fn(d) for name, fn in CHECKS}


# ---- the slice, correct + the three faulted variants -------------------------
def correct() -> Design:
    return Design(
        "correct",
        rails=[
            PowerRail("5V", 5.0, 0.05, sinks=[("psu", 5.0, 0.20)]),          # LDO accepts wide
            PowerRail("3V3", 3.3, 0.05, sinks=[("mcu", 3.3, 0.05), ("sensor", 3.3, 0.05)]),
        ],
        buses=[I2CBus("i2c_bus", nodes=[
            I2CNode("mcu", "controller", provides_pullups=True),
            I2CNode("sensor", "peripheral", address=0x50),
        ])],
    )


def fault1_power_domain() -> Design:
    d = correct(); d.name = "fault1_power_domain"
    # MCU moved onto the 5V rail
    d.rails[1].sinks = [("sensor", 3.3, 0.05)]
    d.rails[0].sinks.append(("mcu", 3.3, 0.05))
    return d


def fault2_no_pullups() -> Design:
    d = correct(); d.name = "fault2_no_pullups"
    for n in d.buses[0].nodes:
        n.provides_pullups = False
    return d


def fault3_addr_collision() -> Design:
    d = correct(); d.name = "fault3_addr_collision"
    d.buses[0].nodes.append(I2CNode("sensor_b", "peripheral", address=0x50))
    return d


if __name__ == '__main__':
    designs = [correct(), fault1_power_domain(), fault2_no_pullups(), fault3_addr_collision()]
    expect_fail = {"fault1_power_domain": "power-domain",
                   "fault2_no_pullups": "i2c-pullups",
                   "fault3_addr_collision": "i2c-address"}
    all_ok = True
    print(f"{'design':<24} {'power':<6} {'pulls':<6} {'addr':<6} verdict")
    print("-" * 56)
    for d in designs:
        res = validate(d)
        flags = {"power-domain": res["power-domain"],
                 "i2c-pullups": res["i2c-pullups"],
                 "i2c-address": res["i2c-address"]}
        cols = "".join(f"{'FAIL' if flags[k] else 'ok':<6} "
                       for k in ("power-domain", "i2c-pullups", "i2c-address"))
        failing = [k for k, v in flags.items() if v]
        if d.name == "correct":
            ok = not failing
        else:
            ok = failing == [expect_fail[d.name]]   # exactly the intended fault, nothing else
        all_ok &= ok
        print(f"{d.name:<24} {cols} {'PASS' if ok else 'UNEXPECTED'}")
        for msgs in flags.values():
            for m in msgs:
                print(f"    └─ {m}")
    print("-" * 56)
    print("RESULT:", "PASS — validator caught exactly the injected faults" if all_ok
          else "FAIL — unexpected result")
    raise SystemExit(0 if all_ok else 1)
