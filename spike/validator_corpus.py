"""Adversarial validator corpus — measure what the gate catches *and what it misses*.

GAPS.md §4c: "the validator was only ever tested on faults its authors designed it
to catch — no measured false-negative rate on real buggy designs. The 'trust layer'
claim needs evidence beyond hand-picked faults."

This harness answers that with a number. It runs a labelled corpus through
`seam_validator.validate()` and classifies every design:

  good            — must pass clean (a failure here is a false POSITIVE → regression)
  bad_covered     — a fault the gate claims to catch; must fire the expected check
                    (a miss here is a regression → CI fails)
  bad_uncovered   — a real, known-bad design the gate currently has NO check for. We
                    EXPECT it to slip through; that is a measured false NEGATIVE. These
                    do not fail CI — they are the honest roadmap of what's left to build.

The `bad_uncovered` set keeps the reported false-negative rate honest: faults *outside*
the ones the validator was built around, that we expect to slip through. CI gates on
regressions (good FP / covered miss); the FN inventory is published, not hidden. As of
the power-connectivity + i2c-multimaster checks that set is empty (measured FN rate
0/9), but the category is retained: the next representable fault we find lives here
until its check exists.

Run:  python3 validator_corpus.py
"""
from __future__ import annotations

import sys

import seam_validator as sv


# ---- a fully-populated GOOD baseline (every deeper-check field set) -----------
def good_baseline() -> sv.Design:
    d = sv.Design(
        "good_baseline",
        rails=[
            sv.PowerRail("5V", 5.0, 0.05, sinks=[("psu", 5.0, 0.20)]),
            sv.PowerRail("3V3", 3.3, 0.05,
                         sinks=[("mcu", 3.3, 0.05), ("sensor", 3.3, 0.05)],
                         source_capacity_ma=800, loads=[("mcu", 50), ("sensor", 5)]),
        ],
        buses=[sv.I2CBus("i2c", nodes=[
            sv.I2CNode("mcu", "controller", provides_pullups=True),
            sv.I2CNode("sensor", "peripheral", address=0x50),
        ], pullup_ohms=4700, speed_hz=100_000)],
    )
    sv.assign_addresses(d)
    return d


def spi_baseline() -> sv.Design:
    """A clean SPI design: an MCU controller + one flash peripheral on its own CS."""
    return sv.Design(
        "good_spi_node",
        rails=[
            sv.PowerRail("5V", 5.0, 0.05, sinks=[("psu", 5.0, 0.20)]),
            sv.PowerRail("3V3", 3.3, 0.05, sinks=[("mcu", 3.3, 0.05), ("flash", 3.3, 0.05)]),
        ],
        spi_buses=[sv.SPIBus("spi_bus", nodes=[
            sv.SPINode("mcu", "controller", mode=0),
            sv.SPINode("flash", "peripheral", chip_select="cs0", mode=0),
        ])],
    )


def _bad_spi_no_controller() -> sv.Design:
    d = spi_baseline(); d.name = "bad_spi_no_controller"
    d.spi_buses[0].nodes = [n for n in d.spi_buses[0].nodes if n.role != "controller"]
    return d


def _bad_spi_cs_collision() -> sv.Design:
    d = spi_baseline(); d.name = "bad_spi_cs_collision"
    d.rails[1].sinks.append(("flash_b", 3.3, 0.05))   # power it: single-fault
    d.spi_buses[0].nodes.append(sv.SPINode("flash_b", "peripheral", chip_select="cs0", mode=0))
    return d


def _peripheral(b: sv.I2CBus, name: str) -> sv.I2CNode:
    return next(n for n in b.nodes if n.block == name)


# ---- corpus: each entry mutates a fresh baseline ------------------------------
def _good_fast_bus() -> sv.Design:
    d = good_baseline(); d.name = "good_fast_400kHz"
    d.buses[0].speed_hz = 400_000
    d.buses[0].pullup_ohms = 2200          # stiffer pull-up keeps t_r within fast-mode limit
    return d


def _bad_power_domain() -> sv.Design:
    d = good_baseline(); d.name = "bad_power_domain"
    d.rails[1].sinks = [("sensor", 3.3, 0.05)]
    d.rails[0].sinks.append(("mcu", 3.3, 0.05))
    return d


def _bad_no_pullups() -> sv.Design:
    d = good_baseline(); d.name = "bad_no_pullups"
    for n in d.buses[0].nodes:
        n.provides_pullups = False
    return d


def _bad_addr_collision() -> sv.Design:
    d = good_baseline(); d.name = "bad_addr_collision"
    d.rails[1].sinks.append(("sensor_b", 3.3, 0.05))   # power it: keep this a single-fault case
    d.buses[0].nodes.append(sv.I2CNode("sensor_b", "peripheral", address=0x50))
    return d


def _bad_overcurrent() -> sv.Design:
    d = good_baseline(); d.name = "bad_overcurrent"
    d.rails[1].loads = [("mcu", 50), ("sensor", 5), ("motor", 900)]   # 955mA on an 800mA rail
    return d


def _bad_reserved_address() -> sv.Design:
    d = good_baseline(); d.name = "bad_reserved_address"
    _peripheral(d.buses[0], "sensor").address = 0x7A                  # in the reserved 0x78..0x7F band
    return d


def _bad_bus_timing() -> sv.Design:
    d = good_baseline(); d.name = "bad_bus_timing"
    d.buses[0].speed_hz = 400_000
    d.buses[0].pullup_ohms = 47_000        # way too weak: RC rise time blows the 300ns fast limit
    return d


# -- former measured false-negatives, now CLOSED (covered regression guards) ----
def _bad_multimaster() -> sv.Design:
    d = good_baseline(); d.name = "bad_multimaster"
    d.rails[1].sinks.append(("mcu2", 3.3, 0.05))   # power it: isolate the multimaster fault
    d.buses[0].nodes.append(sv.I2CNode("mcu2", "controller", provides_pullups=False))
    return d


def _bad_floating_power() -> sv.Design:
    d = good_baseline(); d.name = "bad_floating_power"
    # an active device on the bus that no rail powers. check_power_connectivity now
    # catches this; this fixture is its regression guard.
    d.buses[0].nodes.append(sv.I2CNode("orphan", "peripheral", address=0x51))
    return d


def _bad_part_rail_rating() -> sv.Design:
    d = good_baseline(); d.name = "bad_part_rail_rating"
    # a 5V-only part placed on the 3.3V rail. Its block YAML may claim 'voltage: 3.3'
    # (so power-domain passes), but the part's GROUND-TRUTH datasheet range is 4.5–5.5V.
    # build_design(..., snapshot) attaches that range; check_part_rail_rating then sees
    # the 3.3V rail is below the part's real minimum. (Was a measured FN before #post.)
    d.rails[1].sinks.append(("hv_only_sensor", 3.3, 0.05))
    d.rails[1].part_ratings.append(("hv_only_sensor", 4.5, 5.5))   # from the part-data snapshot
    d.buses[0].nodes.append(sv.I2CNode("hv_only_sensor", "peripheral", address=0x52))
    return d


CORPUS = [
    # good
    {"build": good_baseline,    "kind": "good", "expect": set(), "note": "nominal sensor node"},
    {"build": _good_fast_bus,   "kind": "good", "expect": set(), "note": "400kHz, stiff pull-up — timing OK"},
    {"build": spi_baseline, "kind": "good", "expect": set(), "note": "SPI: MCU + flash, distinct CS"},
    # bad SPI, covered
    {"build": _bad_spi_cs_collision, "kind": "bad_covered", "expect": {"spi-chip-select-unique"},
     "note": "two SPI peripherals share CS cs0"},
    {"build": _bad_spi_no_controller, "kind": "bad_covered", "expect": {"spi-single-controller"},
     "note": "SPI bus with no master"},
    # bad, covered (regression guards — must fire the named check)
    {"build": _bad_power_domain,   "kind": "bad_covered", "expect": {"power-domain"},      "note": "MCU on 5V rail"},
    {"build": _bad_no_pullups,     "kind": "bad_covered", "expect": {"i2c-pullups"},       "note": "no SCL/SDA pull-up"},
    {"build": _bad_addr_collision, "kind": "bad_covered", "expect": {"i2c-address"},       "note": "duplicate 0x50"},
    {"build": _bad_overcurrent,    "kind": "bad_covered", "expect": {"current-budget"},    "note": "955mA on 800mA rail"},
    {"build": _bad_reserved_address,"kind": "bad_covered","expect": {"i2c-reserved-addr"}, "note": "address 0x7A reserved"},
    {"build": _bad_bus_timing,     "kind": "bad_covered", "expect": {"i2c-bus-timing"},    "note": "47kΩ pull-up @400kHz"},
    {"build": _bad_part_rail_rating,"kind": "bad_covered","expect": {"part-rail-rating"},  "note": "5V-only part on the 3.3V rail (vs ground truth)"},
    # formerly UNCOVERED FNs, now COVERED by the two new checks (regression guards)
    {"build": _bad_multimaster, "kind": "bad_covered", "expect": {"i2c-multimaster"},
     "note": "two controllers on one bus — i2c-multimaster must fire"},
    {"build": _bad_floating_power, "kind": "bad_covered", "expect": {"power-connectivity"},
     "note": "active device on no rail — power-connectivity must fire"},
]

# Faults not even representable in today's model — listed so the roadmap is complete.
NOT_MODELLED = [
    "decoupling-adequacy (per-pin bypass caps not modelled)",
    "absolute-max ratings / reverse-polarity (only operating range is modelled)",
    "pin-level ERC on the composed netlist (SKiDL ERC never wired into the gate)",
    "thermal / power-dissipation budget",
    "bus speed vs the slowest participant's max clock",
]


def run() -> bool:
    print("Adversarial validator corpus\n" + "=" * 78)
    good_n = good_fp = 0
    cov_n = cov_hit = 0
    unc_n = unc_fn = unc_surprise = 0
    regressions: list[str] = []

    for e in CORPUS:
        d = e["build"]()
        res = sv.validate(d)
        failing = sorted(k for k, v in res.items() if v)
        kind = e["kind"]

        if kind == "good":
            good_n += 1
            ok = not failing
            if not ok:
                good_fp += 1
                regressions.append(f"FALSE POSITIVE: good '{d.name}' failed {failing}")
            verdict = "ok (clean)" if ok else f"FALSE POSITIVE {failing}"
        elif kind == "bad_covered":
            cov_n += 1
            expect = e["expect"]
            hit = expect.issubset(set(failing))
            if hit:
                cov_hit += 1
                verdict = f"caught [{','.join(failing)}]"
            else:
                regressions.append(f"MISSED: bad '{d.name}' expected {sorted(expect)}, got {failing}")
                verdict = f"MISSED expected {sorted(expect)}, got {failing or '∅'}"
        else:  # bad_uncovered
            unc_n += 1
            if failing:
                unc_surprise += 1
                verdict = f"now caught [{','.join(failing)}] — reclassify as covered"
            else:
                unc_fn += 1
                verdict = f"FALSE NEGATIVE (missing check: {e['missing']})"

        tag = {"good": "GOOD", "bad_covered": "BAD ", "bad_uncovered": "BAD?"}[kind]
        print(f"  [{tag}] {d.name:<32} {verdict}")
        print(f"         └─ {e['note']}")

    total_bad = cov_n + unc_n
    fn_rate = unc_fn / total_bad if total_bad else 0.0
    print("\n" + "=" * 78)
    print(f"good designs:        {good_n:2d}   ({good_fp} false positives)")
    print(f"covered faults:      {cov_n:2d}   detected {cov_hit}/{cov_n}")
    print(f"uncovered faults:    {unc_n:2d}   still-missed {unc_fn}, newly-caught {unc_surprise}")
    print(f"measured false-negative rate (of all {total_bad} known-bad designs): "
          f"{unc_fn}/{total_bad} = {fn_rate:.0%}")
    print("\nmeasured false negatives (representable, the next checks to build):")
    for e in CORPUS:
        if e["kind"] == "bad_uncovered":
            print(f"  · {e['missing']:<26} — {e['note']}")
    print("not modelled at all (further out on the roadmap):")
    for m in NOT_MODELLED:
        print(f"  · {m}")

    ok = not regressions
    print("\n" + "-" * 78)
    if regressions:
        print("REGRESSIONS (these fail CI):")
        for r in regressions:
            print(f"  ✗ {r}")
    print("RESULT:", "PASS — no regressions; FN inventory published above" if ok
          else "FAIL — a covered fault regressed")
    return ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(0 if run() else 1)
