"""Routing pipeline orchestration + pure output parsers (SPEC-ROUTING.md §3).

The tool wrappers (ato/kicad-cli/freerouting) only run in CI; the PARSERS here are
pure and tested offline against fixtures, so a regression in 'did it route / is it
DRC-clean / are the copper layers present' is caught without the heavy toolchain.

Run:  python3 route.py --selftest          # offline, against committed fixtures
      python3 route.py --pipeline ...      # full pipeline (Task 4 — not yet implemented)
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE / "fixtures" / "verified"


# ---------------------------------------------------------------------------
# Pure parsers — no I/O, no subprocess; tested offline in selftest()
# ---------------------------------------------------------------------------

def parse_unrouted(freerouting_log: str) -> int:
    """Return the count of unrouted/incomplete connections freerouting reports.

    Scans for 'incomplete: N', 'N incomplete', or 'unrouted: N' (case-insensitive).
    Raises ValueError if no completion summary is found.
    """
    for pat in (
        r"incomplete[:\s]+(\d+)",
        r"(\d+)\s+incomplete",
        r"unrouted[:\s]+(\d+)",
    ):
        m = re.search(pat, freerouting_log, re.I)
        if m:
            return int(m.group(1))
    raise ValueError("no completion summary found in freerouting log")


def parse_drc(drc_json: str) -> list[dict]:
    """Return error-severity DRC violations from kicad-cli pcb drc --format json output."""
    doc = json.loads(drc_json)
    out = []
    for v in doc.get("violations", []):
        if v.get("severity", "error") == "error":
            out.append(v)
    return out


def gerber_layers_present(names: list[str]) -> set[str]:
    """Classify a list of exported file names into the layers we require."""
    want = {
        "F_Cu": r"F_Cu",
        "B_Cu": r"B_Cu",
        "Edge_Cuts": r"Edge_Cuts",
        "drill": r"\.drl$",
    }
    return {k for k, pat in want.items() if any(re.search(pat, n) for n in names)}


REQUIRED_LAYERS: set[str] = {"F_Cu", "B_Cu", "Edge_Cuts", "drill"}


# ---------------------------------------------------------------------------
# Offline self-test — runs against committed fixture files in fixtures/verified/
# ---------------------------------------------------------------------------

def selftest() -> bool:
    ok = True
    print("route parsers self-test\n" + "-" * 60)

    # parse_unrouted: ok fixture → 0, bad fixture → >0
    u0 = parse_unrouted((FIX / "freerouting.ok.txt").read_text())
    ok_u0 = u0 == 0
    print(f"  [{'ok' if ok_u0 else 'FAIL'}] ok log -> {u0} unrouted (want 0)")
    ok &= ok_u0

    ub = parse_unrouted((FIX / "freerouting.bad.txt").read_text())
    ok_ub = ub > 0
    print(f"  [{'ok' if ok_ub else 'FAIL'}] bad log -> {ub} unrouted (want >0)")
    ok &= ok_ub

    # parse_drc: clean fixture → empty list
    v = parse_drc((FIX / "drc.json").read_text())
    ok_drc = v == []
    print(f"  [{'ok' if ok_drc else 'FAIL'}] clean drc.json -> {len(v)} violations (want 0)")
    ok &= ok_drc

    # gerber_layers_present: gerbers.txt must cover all REQUIRED_LAYERS
    names = (FIX / "gerbers.txt").read_text().split()
    present = gerber_layers_present(names)
    full = REQUIRED_LAYERS <= present
    print(
        f"  [{'ok' if full else 'FAIL'}] gerber set has required layers "
        f"{sorted(present)} (want {sorted(REQUIRED_LAYERS)})"
    )
    ok &= full

    print("-" * 60)
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)

    # Full pipeline entrypoint is added in Task 4.
    raise SystemExit(
        "route.py: pipeline mode not yet implemented (Task 4). "
        "Use --selftest to run the offline parser tests."
    )
