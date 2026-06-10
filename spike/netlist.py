"""Netlist-equivalence guard — prove a board's *connectivity* is unchanged.

The route gate proves a board ROUTES (0 unrouted / 0 DRC); it does NOT prove the netlist
is what we intended. This reduces a built `.kicad_pcb` to a canonical connectivity form
that drops net names and reference designators (which shift cosmetically when the .ato
hierarchy changes) but keeps every part and every pad-to-net membership. A dropped cap, a
mis-wired pin, or a pin that floats when it shouldn't all change the canonical form.

Run:  python3 netlist.py --selftest
      python3 netlist.py --emit  IN.kicad_pcb              # canonical JSON to stdout
      python3 netlist.py --check IN.kicad_pcb golden.json  # exit 1 + diff on mismatch
"""
from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "verified" / "verified.kicad_pcb"

_FP_RE = re.compile(r'\(footprint "([^"]+)"')      # footprint lib id = MANUF_PART:PACKAGE
_VAL_RE = re.compile(r'\(property "Value" "([^"]*)"')
_PAD_RE = re.compile(r'\(pad "([^"]*)"')
_NET_RE = re.compile(r'\(net (\d+) "([^"]*)"')


def _iter_footprint_blocks(text: str):
    """Yield each top-level (footprint ...) block's text (depth-counted s-expr)."""
    i = 0
    while True:
        i = text.find("(footprint", i)
        if i < 0:
            return
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield text[i:j + 1]
                    break
            j += 1
        i = j + 1


def canonical(text: str) -> dict:
    """Reduce a .kicad_pcb to a name/refdes-independent connectivity form:
    {"parts": sorted [libid|value], "nets": sorted [ sorted [libid|value|pad] ]}.
    Net ids/names and reference designators are dropped; pad-to-net *membership* and the
    parts multiset are kept. Net 0 (unconnected pads) is kept as its own group so a pin
    that floats when it shouldn't is caught."""
    nets: dict[int, list[str]] = {}
    parts: list[str] = []
    for block in _iter_footprint_blocks(text):
        mfp = _FP_RE.search(block)
        libid = mfp.group(1) if mfp else "?"
        mval = _VAL_RE.search(block)
        value = mval.group(1) if mval else ""
        parts.append(f"{libid}|{value}")
        # Linear scan: a (pad "X") line starts a pad; the (net N "...") line that follows
        # within its block attaches to it. A pad with no net line stays net 0 (unconnected).
        pads: list[tuple[str, int]] = []
        cur_pad: str | None = None
        cur_net = 0
        for line in block.splitlines():
            mp = _PAD_RE.search(line)
            if mp:
                if cur_pad is not None:
                    pads.append((cur_pad, cur_net))
                cur_pad, cur_net = mp.group(1), 0
                continue
            mn = _NET_RE.search(line)
            if mn and cur_pad is not None:
                cur_net = int(mn.group(1))
        if cur_pad is not None:
            pads.append((cur_pad, cur_net))
        for pad_name, net_id in pads:
            nets.setdefault(net_id, []).append(f"{libid}|{value}|{pad_name}")
    return {"parts": sorted(parts),
            "nets": sorted(sorted(members) for members in nets.values())}


def dumps(canon: dict) -> str:
    return json.dumps(canon, indent=2, sort_keys=True, ensure_ascii=True)


def diff(got: dict, want: dict) -> list[str]:
    """Human-readable multiset diff (+ = in build only, - = in golden only)."""
    out: list[str] = []
    cg, cw = Counter(got["parts"]), Counter(want["parts"])
    for p in sorted((cg - cw).elements()):
        out.append(f"  + part {p}")
    for p in sorted((cw - cg).elements()):
        out.append(f"  - part {p}")
    ng, nw = Counter(map(tuple, got["nets"])), Counter(map(tuple, want["nets"]))
    for n in (ng - nw).elements():
        out.append(f"  + net {list(n)}")
    for n in (nw - ng).elements():
        out.append(f"  - net {list(n)}")
    return out


def check(board_pcb: Path, golden_json: Path) -> bool:
    got = canonical(board_pcb.read_text(encoding="utf-8"))
    want = json.loads(golden_json.read_text(encoding="utf-8"))
    if got == want:
        print(f"  [ok] {board_pcb.name} connectivity matches {golden_json.name}")
        return True
    print(f"  [FAIL] {board_pcb.name} connectivity differs from {golden_json.name}:")
    for line in diff(got, want):
        print(line)
    return False


def selftest() -> bool:
    text = FIXTURE.read_text(encoding="utf-8")
    c1, c2 = canonical(text), canonical(text)
    ok = True
    det = dumps(c1) == dumps(c2)
    print(f"  [{'ok' if det else 'FAIL'}] deterministic emit"); ok &= det
    sane = len(c1["parts"]) >= 1 and len(c1["nets"]) >= 1
    print(f"  [{'ok' if sane else 'FAIL'}] {len(c1['parts'])} parts, "
          f"{len(c1['nets'])} nets parsed"); ok &= sane
    roundtrip = json.loads(dumps(c1)) == c1
    print(f"  [{'ok' if roundtrip else 'FAIL'}] JSON round-trip stable"); ok &= roundtrip
    # a connectivity change must be detected (drop one net)
    mutated = {"parts": c1["parts"], "nets": c1["nets"][1:]}
    detects = c1 != mutated and bool(diff(mutated, c1))
    print(f"  [{'ok' if detects else 'FAIL'}] a connectivity change is detected"); ok &= detects
    print("-" * 60); print("SELFTEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    if "--selftest" in args:
        raise SystemExit(0 if selftest() else 1)
    if args and args[0] == "--emit":
        print(dumps(canonical(Path(args[1]).read_text(encoding="utf-8"))))
        raise SystemExit(0)
    if args and args[0] == "--check":
        raise SystemExit(0 if check(Path(args[1]), Path(args[2])) else 1)
    print(__doc__)
    raise SystemExit(2)
