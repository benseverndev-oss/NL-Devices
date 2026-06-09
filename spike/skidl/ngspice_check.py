"""Minimal BSD-clean ngspice driver for the spike's electrical-sanity leg.

PySpice 1.5 is incompatible with ngspice 42 (confirmed in step 0), so we drive
the ngspice binary directly. ngspice is BSD-licensed -> safe to embed, unlike
the GPLv3 PySpice. This is the op-point sanity primitive the validator will use.
"""
import re, subprocess, tempfile, os

def op_point(netlist: str, nodes: list[str]) -> dict[str, float]:
    """Run a DC operating point on a SPICE `netlist` string, return node voltages."""
    prints = "\n".join(f"print v({n})" for n in nodes)
    deck = f"{netlist}\n.control\nop\n{prints}\n.endc\n.end\n"
    with tempfile.NamedTemporaryFile('w', suffix='.cir', delete=False) as f:
        f.write(deck); path = f.name
    try:
        out = subprocess.run(['ngspice', '-b', path], capture_output=True,
                             text=True, timeout=30).stdout
    finally:
        os.unlink(path)
    res = {}
    for n in nodes:
        m = re.search(rf'v\({re.escape(n)}\)\s*=\s*([-\d.eE+]+)', out, re.IGNORECASE)
        if m: res[n] = float(m.group(1))
    return res

if __name__ == '__main__':
    # Hello-world: 5V across 10k/10k divider -> MID = 2.5V
    nl = "* divider\nVin VIN 0 5\nR1 VIN MID 10k\nR2 MID 0 10k"
    v = op_point(nl, ['MID'])
    print(f"V(MID) = {v['MID']:.4f} V")
    assert abs(v['MID'] - 2.5) < 1e-3, "FAIL"
    print("PASS: ngspice op-point sanity primitive OK (PySpice-free, BSD-clean)")
