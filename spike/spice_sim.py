"""Genuine ngspice transient simulations — the electrical checks that actually need
a simulator, and the proof that the analytic limits used elsewhere are sound.

GAPS.md §3 / §5 item 6: the old "electrical gate" decks were an ideal source behind a
0.1Ω resistor and a resistor divider — Ohm's law dressed as SPICE, where the real
pass/fail was the arithmetic beside them. This module replaces that theatre with real
`.tran` runs whose results a calculator can't produce directly:

  * `sim_i2c_rise_ns`  — the RC rise time of an open-drain I2C line (charge curve),
                         measured 30%→70% (the I2C-spec definition).
  * `sim_rail_droop_v` — a rail's transient droop under a load-current step with finite
                         decoupling (the charge the bulk cap must supply).

Honesty by construction: the rise-time sim is cross-checked against the analytic
`t_r ≈ 0.8473·R·C` that `seam_validator.check_i2c_bus_capacitance` uses — so the cheap
always-on analytic limit is *validated* by a real simulation, and we can say which is
which. ngspice is BSD-licensed; we drive the binary directly (no GPLv3 PySpice).

Run:  python3 spice_sim.py --selftest      # live sims if ngspice present; else parser+analytic only
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

NGSPICE = shutil.which("ngspice")


def ngspice_available() -> bool:
    return NGSPICE is not None


# ---- driver ------------------------------------------------------------------
def _run_deck(deck: str, timeout: int = 30) -> str:
    """Run a full ngspice deck (with its own .control/.end) in batch mode -> stdout."""
    if not NGSPICE:
        raise RuntimeError("ngspice not on PATH")
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
        f.write(deck)
        path = f.name
    try:
        return subprocess.run([NGSPICE, "-b", path], capture_output=True,
                              text=True, timeout=timeout).stdout
    finally:
        os.unlink(path)


def _parse_meas(out: str, name: str) -> float | None:
    """Pull a `.meas` result (`name = 1.23e-07 ...`) from ngspice batch output."""
    m = re.search(rf'\b{re.escape(name)}\s*=\s*([-+0-9.eE]+)', out, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# ---- analytic references (no simulator needed) -------------------------------
def analytic_i2c_rise_ns(r_ohms: float, c_pf: float) -> float:
    """I2C 30%→70% rise time of an RC line. t_r = ln(0.7/0.3)·R·C ≈ 0.8473·R·C."""
    return 0.8473 * r_ohms * c_pf * 1e-3   # R(Ω)·C(pF) -> ns


# ---- real transient sims -----------------------------------------------------
def sim_i2c_rise_ns(r_ohms: float, c_pf: float, vcc: float = 3.3) -> float | None:
    """Open-drain I2C line released at t=0 and pulled up through R into C. Returns the
    ngspice-measured 30%→70% rise time in ns (None if the measurement didn't resolve)."""
    tau = r_ohms * c_pf * 1e-12
    stop, step = 12 * tau, 12 * tau / 4000
    deck = (
        "* i2c open-drain rise\n"
        f"Vcc vcc 0 {vcc}\n"
        f"Rp vcc sda {r_ohms}\n"
        f"Csda sda 0 {c_pf}p\n"
        ".ic v(sda)=0\n"
        ".control\n"
        f"tran {step:.4e} {stop:.4e} uic\n"
        f"meas tran trise TRIG v(sda) VAL={0.3 * vcc:.5f} RISE=1 "
        f"TARG v(sda) VAL={0.7 * vcc:.5f} RISE=1\n"
        ".endc\n.end\n"
    )
    t = _parse_meas(_run_deck(deck), "trise")
    return t * 1e9 if t is not None else None


def sim_rail_droop_v(vnom: float, rout_ohms: float, c_uf: float, istep_ma: float,
                     pulse_ns: float = 200.0) -> float | None:
    """Rail = ideal Vnom behind output impedance Rout, with c_uf of decoupling. A load
    pulse of istep_ma for pulse_ns forces the cap to supply charge. Returns the
    ngspice-measured minimum rail voltage (the droop) in volts."""
    istep_a = istep_ma / 1000.0
    t0, edge, width = 1e-6, 10e-9, pulse_ns * 1e-9
    stop, step = 3e-6, 1e-9
    deck = (
        "* rail droop under a load step\n"
        f"Vreg vreg 0 {vnom}\n"
        f"Rout vreg rail {rout_ohms}\n"
        f"Cbulk rail 0 {c_uf}u\n"
        f"Iload rail 0 PULSE(0 {istep_a:.4f} {t0:.3e} {edge:.3e} {edge:.3e} {width:.3e} 1)\n"
        ".control\n"
        f"tran {step:.3e} {stop:.3e}\n"
        f"meas tran vmin MIN v(rail) FROM={t0:.3e} TO={(t0 + width + 1e-6):.3e}\n"
        ".endc\n.end\n"
    )
    return _parse_meas(_run_deck(deck), "vmin")


# ---- self-test: prove the sims have teeth AND match the analytic limit --------
_SAMPLE_MEAS = (
    "Circuit: * i2c open-drain rise\n"
    "trise               =  1.589430e-07 targ=  1.073900e-06 trig=  9.149600e-07\n"
    "vmin                =  2.901300e+00 at=  1.050000e-06\n"
)


def selftest() -> bool:
    ok = True
    print("spice_sim self-test\n" + "-" * 70)

    # 1) parser handles real ngspice .meas output format (always runnable)
    pr = _parse_meas(_SAMPLE_MEAS, "trise")
    p_ok = pr is not None and abs(pr - 1.589430e-07) < 1e-12
    ok &= p_ok
    print(f"  [{'ok' if p_ok else 'FAIL'}] meas parser: trise -> {pr}")

    # 2) analytic reference sanity (always)
    a = analytic_i2c_rise_ns(4700, 40)
    a_ok = 150 < a < 170
    ok &= a_ok
    print(f"  [{'ok' if a_ok else 'FAIL'}] analytic 4.7kΩ·40pF rise = {a:.0f}ns (expect ~159)")

    if not ngspice_available():
        print("  [skip] ngspice not on PATH — live .tran sims run in CI. "
              "Parser + analytic verified above.")
        print("-" * 70)
        print("SELFTEST:", "PASS (offline subset)" if ok else "FAIL")
        return ok

    # 3) LIVE: I2C rise sim agrees with analytic within 5%, and weak pull-up fails fast mode
    sim = sim_i2c_rise_ns(4700, 40)
    cross_ok = sim is not None and abs(sim - a) / a < 0.05
    ok &= cross_ok
    print(f"  [{'ok' if cross_ok else 'FAIL'}] sim rise {sim:.0f}ns vs analytic {a:.0f}ns "
          f"(<5% — real .tran validates the analytic limit)")
    weak = sim_i2c_rise_ns(47000, 40)
    weak_ok = weak is not None and weak > 300.0      # blows the 300ns fast-mode limit
    ok &= weak_ok
    print(f"  [{'ok' if weak_ok else 'FAIL'}] weak 47kΩ pull-up rise {weak:.0f}ns > 300ns (caught)")

    # 4) LIVE: rail droop — adequate decoupling holds, under-decoupling sags out of tol
    good = sim_rail_droop_v(3.3, 0.1, 100.0, 200)        # 100µF bulk
    good_ok = good is not None and good >= 3.3 * 0.95
    ok &= good_ok
    print(f"  [{'ok' if good_ok else 'FAIL'}] 100µF rail droop floor {good:.3f}V ≥ 3.135V (holds)")
    bad = sim_rail_droop_v(3.3, 0.1, 0.1, 200)           # only 100nF
    bad_ok = bad is not None and bad < 3.3 * 0.95
    ok &= bad_ok
    print(f"  [{'ok' if bad_ok else 'FAIL'}] 100nF rail droop floor {bad:.3f}V < 3.135V (caught)")

    print("-" * 70)
    print("SELFTEST:", "PASS — real ngspice sims have teeth and match the analytic limit"
          if ok else "FAIL")
    return ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(0 if selftest() else 1)
