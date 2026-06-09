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
    source_capacity_ma: float | None = None   # max current the source can deliver (None = unmodeled)
    loads: list[tuple[str, float]] = field(default_factory=list)  # (block, current_ma) drawn from this rail
    # (block, gt_vmin, gt_vmax): each sink's GROUND-TRUTH datasheet operating range,
    # so the rail can be checked against what the real part tolerates — not the
    # (possibly wrong) hand-typed YAML. None on a bound = that side is open.
    part_ratings: list[tuple[str, float | None, float | None]] = field(default_factory=list)


@dataclass
class I2CNode:
    block: str
    role: str                # 'controller' | 'peripheral'
    provides_pullups: bool = False
    address: int | None = None   # 7-bit address (assigned from the range below)
    addr_base: int | None = None # lowest strappable address
    addr_bits: int = 0           # number of address pins -> range = 2**addr_bits
    pin_cap_pf: float = 10.0     # device SCL/SDA pin capacitance (I2C spec budgets 10pF/pin)


@dataclass
class I2CBus:
    name: str
    nodes: list[I2CNode] = field(default_factory=list)
    speed_hz: int = 100_000           # target SCL frequency (100k standard / 400k fast / 1M Fm+)
    pullup_ohms: float | None = None  # bus pull-up resistance (None = unmodeled, skips timing check)
    stray_cap_pf: float = 20.0        # board/trace stray capacitance budget


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


# ---- deeper rating / electrical checks (validator-depth pass, GAPS §4c) ------
# These fire only when the design carries the relevant data (current budget,
# pull-up value, ...). Absent data -> the check is skipped, never a false alarm.
I2C_RESERVED_LO = 0x07    # 0x00..0x07 reserved (general call, CBUS, ...)
I2C_RESERVED_HI = 0x78    # 0x78..0x7F reserved (10-bit, device-ID, ...)
I2C_MAX_BUS_CAP_PF = 400.0
I2C_RISE_LIMIT_NS = {100_000: 1000.0, 400_000: 300.0, 1_000_000: 120.0}  # t_r max per mode


def check_current_budget(d: Design) -> list[str]:
    """A rail must not be asked to source more current than it can deliver."""
    errs = []
    for r in d.rails:
        if r.source_capacity_ma is None or not r.loads:
            continue
        total = sum(c for _, c in r.loads)
        if total > r.source_capacity_ma:
            who = ", ".join(f"{b}:{c:.0f}mA" for b, c in r.loads)
            errs.append(
                f"POWER: rail '{r.name}' draws {total:.0f}mA ({who}) > source capacity "
                f"{r.source_capacity_ma:.0f}mA")
    return errs


def check_i2c_reserved_addresses(d: Design) -> list[str]:
    """Assigned addresses must be valid 7-bit and outside the I2C reserved ranges."""
    errs = []
    for b in d.buses:
        for n in b.nodes:
            if n.role != 'peripheral' or n.address is None:
                continue
            a = n.address
            if not (0 <= a <= 0x7F):
                errs.append(f"I2C: bus '{b.name}' '{n.block}' address 0x{a:02X} is not a valid 7-bit address")
            elif a <= I2C_RESERVED_LO or a >= I2C_RESERVED_HI:
                errs.append(f"I2C: bus '{b.name}' '{n.block}' address 0x{a:02X} is in a reserved I2C range")
    return errs


def check_i2c_bus_capacitance(d: Design) -> list[str]:
    """Bus capacitance must stay within spec, and (if the pull-up is known) the RC
    rise time must meet the target-speed limit. t_r ≈ 0.8473·R·C (10%→90%)."""
    errs = []
    for b in d.buses:
        if not b.nodes:
            continue
        cap_pf = sum(n.pin_cap_pf for n in b.nodes) + b.stray_cap_pf
        if cap_pf > I2C_MAX_BUS_CAP_PF:
            errs.append(f"I2C: bus '{b.name}' est. capacitance {cap_pf:.0f}pF exceeds "
                        f"{I2C_MAX_BUS_CAP_PF:.0f}pF spec maximum")
        if b.pullup_ohms:
            t_r_ns = 0.8473 * b.pullup_ohms * cap_pf * 1e-3   # R(Ω)·C(pF) → ns
            limit = I2C_RISE_LIMIT_NS.get(b.speed_hz)
            if limit and t_r_ns > limit:
                errs.append(
                    f"I2C: bus '{b.name}' rise time ~{t_r_ns:.0f}ns "
                    f"(R={b.pullup_ohms:.0f}Ω, C={cap_pf:.0f}pF) exceeds {limit:.0f}ns "
                    f"limit at {b.speed_hz // 1000}kHz")
    return errs


def check_part_rail_rating(d: Design) -> list[str]:
    """Join to the ground-truth part DB: the rail voltage a part *actually sees* must
    fall within that part's datasheet operating range. Catches a part placed on a
    wrong-voltage rail even when the block's hand-typed YAML claims it's fine — the
    headline false negative measured in the validator corpus. Fires only where a
    ground-truth range was attached (see block_contract.build_design with a snapshot)."""
    errs = []
    for r in d.rails:
        lo, hi = _interval(r.source_v, r.source_tol)   # the rail's worst-case excursion
        for block, vmin, vmax in r.part_ratings:
            if vmin is not None and lo < vmin:
                errs.append(f"RATING: rail '{r.name}' ≥{lo:.3f}V drops below '{block}' "
                            f"part minimum {vmin:.3f}V (ground truth)")
            if vmax is not None and hi > vmax:
                errs.append(f"RATING: rail '{r.name}' ≤{hi:.3f}V exceeds '{block}' "
                            f"part maximum {vmax:.3f}V (ground truth)")
    return errs


CHECKS = [("power-domain", check_power_domains),
          ("i2c-pullups", check_i2c_pullups),
          ("i2c-address", check_i2c_addresses),
          ("current-budget", check_current_budget),
          ("i2c-reserved-addr", check_i2c_reserved_addresses),
          ("i2c-bus-timing", check_i2c_bus_capacitance),
          ("part-rail-rating", check_part_rail_rating)]


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
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # box-drawing glyphs on Windows consoles
    except Exception:
        pass
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
