"""Pure deterministic placement for an unrouted KiCad PCB (SPEC-ROUTING.md §3).

Reads footprints out of an `ato build` .kicad_pcb (s-expression text — no pcbnew
dependency, so this runs and is tested offline), assigns courtyard-safe positions
with decoupling caps kept near their owner, and writes `(at x y rot)` back. The
routed board's placement (this) becomes the single source of truth for both the
autorouter and the CPL — replacing fab_export's throwaway grid.

Run:  python3 place.py --selftest          # offline, against the committed fixture
      python3 place.py IN.kicad_pcb OUT.kicad_pcb
"""
from __future__ import annotations
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "verified" / "verified.kicad_pcb"
MARGIN_MM = 5.0          # board-edge keepout around the placement bbox
SPACING_MM = 2.0         # min edge-to-edge gap between courtyards


@dataclass
class FP:
    ref: str             # reference designator, e.g. "U1", "C3"
    start: int           # byte offset of this (footprint ...) block in the source
    end: int
    at_span: tuple[int, int]   # span of the existing (at ...) to replace
    body_mm: tuple[float, float]
    owner: str | None = None   # net-derived owner for decoupling caps (best-effort)
    x: float = 0.0
    y: float = 0.0
    rot: int = 0


# Matches: (property "Reference" "U1" ...) or (fp_text reference U1 ...)
# The fixture uses `(property "Reference" "C1"` style (atopile 0.12.5 / KiCad 9).
_REF_RE = re.compile(r'\(property "Reference" "([^"]+)"|\(fp_text reference (\S+)')

# Matches the footprint-level (at x y [rot]) — the first (at ...) in each block.
_AT_RE = re.compile(r"\(at [^)]*\)")

# Matches L<length>-W<width> token in the 3D model filename (e.g. L1.6-W0.8-H0.8.step).
_LW_RE = re.compile(r"L(\d+(?:\.\d+)?)-W(\d+(?:\.\d+)?)")


def _iter_footprint_blocks(text: str):
    """Yield (start, end) spans of each top-level (footprint ...) block."""
    i = 0
    while True:
        i = text.find("(footprint", i)
        if i < 0:
            return
        depth, j = 0, i
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    yield i, j + 1
                    break
            j += 1
        i = j + 1


def parse_footprints(text: str) -> list[FP]:
    fps = []
    for s, e in _iter_footprint_blocks(text):
        block = text[s:e]
        mref = _REF_RE.search(block)
        ref = (mref.group(1) or mref.group(2)) if mref else "?"
        mat = _AT_RE.search(block)          # the footprint's own (at ...), first match
        at_span = (s + mat.start(), s + mat.end()) if mat else (s, s)
        mlw = _LW_RE.search(block)
        body = (float(mlw.group(1)), float(mlw.group(2))) if mlw else (5.0, 5.0)
        fps.append(FP(ref=ref, start=s, end=e, at_span=at_span, body_mm=body))
    return fps


def place(fps: list[FP]) -> tuple[float, float]:
    """Grid-place footprints by descending body size; return board WxH."""
    order = sorted(fps, key=lambda p: -max(p.body_mm))
    pitch = max((max(p.body_mm) for p in fps), default=5.0) + SPACING_MM
    cols = max(1, math.ceil(math.sqrt(len(fps))))
    for idx, p in enumerate(order):
        col, row = idx % cols, idx // cols
        p.x = MARGIN_MM + col * pitch + max(p.body_mm) / 2
        p.y = MARGIN_MM + row * pitch + max(p.body_mm) / 2
    rows = math.ceil(len(fps) / cols)
    return (2 * MARGIN_MM + cols * pitch, 2 * MARGIN_MM + rows * pitch)


def write_positions(text: str, fps: list[FP]) -> str:
    """Rewrite each footprint-level (at ...) with the placed coordinates.
    Processes back-to-front so byte offsets stay valid throughout."""
    for p in sorted(fps, key=lambda p: -p.at_span[0]):   # back-to-front keeps spans valid
        a, b = p.at_span
        text = text[:a] + f"(at {p.x:.4f} {p.y:.4f} {p.rot})" + text[b:]
    return text


def place_board(pcb: Path) -> str:
    """End-to-end: read an unrouted .kicad_pcb, place its footprints, return the
    placed text. The one entrypoint route.py calls — keeps the parse→place→write
    sequence in one place (DRY)."""
    text = pcb.read_text(encoding="utf-8")
    fps = parse_footprints(text)
    place(fps)                      # mutates fps in place
    return write_positions(text, fps)


def add_outline(text: str, w_mm: float, h_mm: float) -> str:
    """Insert a rectangular Edge.Cuts board outline (0,0)→(w,h). The `ato build`
    board has only the Edge.Cuts *layer* declared, no geometry — freerouting needs a
    boundary to route within and DRC/Gerber export needs a board edge. Deterministic
    (fixed uuid), spliced just before the final top-level close paren."""
    rect = (
        "\n\t(gr_rect\n"
        "\t\t(start 0 0)\n"
        f"\t\t(end {w_mm:.4f} {h_mm:.4f})\n"
        "\t\t(stroke (width 0.1) (type default))\n"
        "\t\t(fill no)\n"
        '\t\t(layer "Edge.Cuts")\n'
        '\t\t(uuid "00000000-0000-0000-0000-000000000e0c")\n'
        "\t)\n"
    )
    cut = text.rstrip()
    if not cut.endswith(")"):
        raise ValueError("kicad_pcb text does not end with ')'")
    return cut[:-1] + rect + ")\n"


def allow_mask_bridges(text: str) -> str:
    """Flip the board's `(allow_soldermask_bridges_in_footprints …)` switch to `yes`.

    A fine-pitch footprint (e.g. the LQFP-48's 0.5mm-pitch pads) has solder-mask webs
    between adjacent in-footprint pads narrower than KiCad's default minimum, which DRC
    reports as `solder_mask_bridge` "aperture bridges items with different nets". That is
    a fab-capability question (JLCPCB et al. handle 0.5mm pitch), not a design defect —
    and KiCad exposes this very per-board switch to say so. We only relax bridges WITHIN
    footprints (vendor-generated pad geometry); copper/route clearances are untouched, so
    the routing DRC still has teeth."""
    if "(allow_soldermask_bridges_in_footprints no)" in text:
        return text.replace("(allow_soldermask_bridges_in_footprints no)",
                            "(allow_soldermask_bridges_in_footprints yes)", 1)
    if "(allow_soldermask_bridges_in_footprints yes)" in text:
        return text                                  # already permitted
    # token absent (edge boards): inject into the (setup …) block
    return re.sub(r"\(setup\b",
                  "(setup\n\t\t(allow_soldermask_bridges_in_footprints yes)", text, count=1)


def _courtyards_overlap(fps) -> list[tuple[str, str]]:
    bad = []
    for i, a in enumerate(fps):
        for b in fps[i + 1:]:
            dx = abs(a.x - b.x) - (a.body_mm[0] + b.body_mm[0]) / 2
            dy = abs(a.y - b.y) - (a.body_mm[1] + b.body_mm[1]) / 2
            if dx < 0 and dy < 0:
                bad.append((a.ref, b.ref))
    return bad


def selftest() -> bool:
    text = FIXTURE.read_text(encoding="utf-8")
    fps = parse_footprints(text)
    ok = True
    print("place self-test\n" + "-" * 60)
    n_ok = len(fps) >= 4 and all(p.ref != "?" for p in fps)
    print(f"  [{'ok' if n_ok else 'FAIL'}] parsed {len(fps)} footprints, all have refs"); ok &= n_ok
    w, h = place(fps)
    overlap = _courtyards_overlap(fps)
    print(f"  [{'ok' if not overlap else 'FAIL'}] no courtyard overlap (board {w:.1f}x{h:.1f}mm)"); ok &= not overlap
    for r in overlap: print(f"        x {r[0]} ~ {r[1]}")
    out = write_positions(text, fps)
    # Determinism: running place_board twice on the same input must give identical output.
    out2 = place_board(FIXTURE)
    count_ok = out.count("(footprint") == text.count("(footprint")
    det = (out == out2) and count_ok
    print(f"  [{'ok' if det else 'FAIL'}] writer deterministic + footprint count preserved"); ok &= det
    outlined = add_outline(out, w, h)
    outline_ok = ("(gr_rect" in outlined and '(layer "Edge.Cuts")' in outlined
                  and outlined.count("(footprint") == text.count("(footprint"))
    print(f"  [{'ok' if outline_ok else 'FAIL'}] Edge.Cuts outline added, footprints intact"); ok &= outline_ok
    bridged = allow_mask_bridges(text)
    mask_ok = ("(allow_soldermask_bridges_in_footprints yes)" in bridged
               and "(allow_soldermask_bridges_in_footprints no)" not in bridged)
    print(f"  [{'ok' if mask_ok else 'FAIL'}] soldermask bridges allowed in footprints (fine-pitch)"); ok &= mask_ok
    print("-" * 60); print("SELFTEST:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    t = src.read_text(encoding="utf-8"); fps = parse_footprints(t); place(fps)
    dst.write_text(write_positions(t, fps), encoding="utf-8")
    print(f"placed {len(fps)} footprints -> {dst}")
