"""Fab-export spike — turn a validated design into a fab-ready package + a dry-run
JLCPCB order. The last mile of "NL → … → a board you can order."

GAPS.md §4e / §5 item 7: there is no fab export yet (Gerbers, BOM/CPL, order API).
This spikes one path end to end, and is honest about the one piece that's genuinely
upstream:

  * **BOM** (`*-bom.csv`)  — JLCPCB format, every line a *real* LCSC part from the
    verified blocks + ground-truth snapshot (this is where GAPS #1/#3 pay off).
  * **CPL** (`*-cpl.csv`)  — JLCPCB centroid/placement, coords from a deterministic
    auto-place sized by each part's real body dimensions (parsed from the snapshot
    package). Placement is a **pre-routing placeholder**, clearly flagged — real
    coordinates come from layout (the §4e gap), not from this spike.
  * **Gerber + drill** — a *format-valid* RS-274X board outline (Edge.Cuts) + Excellon
    drill (mounting holes), derived from the part bounding box. The mechanical outline
    + holes are legitimately derivable now; **copper layers are pending routing** and
    are intentionally not emitted (we don't fake routed copper).
  * **Order** — a JLCPCB assembly-order payload, assembled and **validated**, but
    **dry-run by default**. Submitting is a real, paid transaction; this never POSTs.

Run:  python3 fab_export.py --selftest     # build+validate the sensor_node package
      python3 fab_export.py --out build/fab # write the package to a directory
"""
from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import block_contract
import partdb


def _load_slice(name: str = "sensor_node") -> dict:
    return yaml.safe_load((HERE / "slices" / f"{name}.yaml").read_text())

HERE = Path(__file__).parent
SCALE = 1_000_000          # RS-274X %FSLAX46% → coordinates in 1e-6 mm
GRID_COLS = 2
SPACING_MM = 4.0           # edge-to-edge gap between placed parts
MARGIN_MM = 5.0            # board edge margin around the placement bbox
HOLE_DIA_MM = 3.2          # M3 mounting holes


@dataclass
class Placed:
    refdes: str
    inst: str
    mpn: str
    lcsc: str
    footprint: str
    body_mm: tuple[float, float]
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation: int = 0
    layer: str = "Top"


@dataclass
class Package:
    name: str
    outdir: Path
    parts: list[Placed]
    board_mm: tuple[float, float]
    files: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


# ---- helpers -----------------------------------------------------------------
def _body_dims(package: str | None) -> tuple[float, float]:
    """Parse body L/W (mm) from a snapshot package string, e.g.
    'SOIC-8_L4.9-W3.9-P1.27...' -> (4.9, 3.9). Falls back to 5×5 if unparseable."""
    if package:
        m = re.search(r"L(\d+(?:\.\d+)?)-W(\d+(?:\.\d+)?)", package)
        if m:
            return float(m.group(1)), float(m.group(2))
    return 5.0, 5.0


def _footprint_family(package: str | None) -> str:
    return re.split(r"[_\s]", (package or "").strip())[0] or "UNKNOWN"


def place_parts(parts: list[Placed]) -> tuple[float, float]:
    """Deterministic grid auto-place (pre-routing placeholder). Returns board WxH."""
    pitch = max((max(p.body_mm) for p in parts), default=5.0) + SPACING_MM
    for i, p in enumerate(parts):
        col, row = i % GRID_COLS, i // GRID_COLS
        p.x_mm = MARGIN_MM + col * pitch + max(p.body_mm) / 2
        p.y_mm = MARGIN_MM + row * pitch + max(p.body_mm) / 2
    cols = min(GRID_COLS, len(parts)) or 1
    rows = (len(parts) + GRID_COLS - 1) // GRID_COLS or 1
    return (2 * MARGIN_MM + cols * pitch, 2 * MARGIN_MM + rows * pitch)


# ---- file writers ------------------------------------------------------------
def _write_bom(path: Path, parts: list[Placed]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for p in parts:
            w.writerow([p.mpn, p.refdes, p.footprint, p.lcsc])


def _write_cpl(path: Path, parts: list[Placed]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in parts:
            w.writerow([p.refdes, f"{p.x_mm:.3f}mm", f"{p.y_mm:.3f}mm", p.layer, p.rotation])


def _write_edge_cuts(path: Path, w_mm: float, h_mm: float) -> None:
    def c(mm: float) -> int:
        return int(round(mm * SCALE))
    pts = [(0, 0), (w_mm, 0), (w_mm, h_mm), (0, h_mm), (0, 0)]
    lines = ["%FSLAX46Y46*%", "%MOMM*%", "%ADD10C,0.150*%", "G01*", "D10*"]
    lines.append(f"X{c(pts[0][0])}Y{c(pts[0][1])}D02*")        # move to start
    for x, y in pts[1:]:
        lines.append(f"X{c(x)}Y{c(y)}D01*")                    # draw, closing the loop
    lines.append("M02*")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_drill(path: Path, w_mm: float, h_mm: float) -> None:
    inset = MARGIN_MM
    holes = [(inset, inset), (w_mm - inset, inset),
             (w_mm - inset, h_mm - inset), (inset, h_mm - inset)]
    lines = ["M48", "METRIC,TZ", f"T1C{HOLE_DIA_MM:.3f}", "%", "T1"]
    for x, y in holes:
        lines.append(f"X{x:.3f}Y{y:.3f}")
    lines.append("M30")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- build -------------------------------------------------------------------
def build_package(slice_doc: dict, blocks: dict, snapshot: dict, outdir: Path) -> Package:
    outdir.mkdir(parents=True, exist_ok=True)
    name = slice_doc["name"]
    parts: list[Placed] = []
    for i, (inst, bid) in enumerate(slice_doc["instances"].items(), start=1):
        b = blocks[bid]
        bp = b.bound_part or {}
        gt = snapshot.get(bp.get("lcsc"))
        pkg = (gt.package if gt else None) or bp.get("footprint")
        parts.append(Placed(
            refdes=f"U{i}", inst=inst, mpn=bp.get("mpn", b.id), lcsc=bp.get("lcsc", ""),
            footprint=_footprint_family(pkg), body_mm=_body_dims(pkg)))
    w_mm, h_mm = place_parts(parts)

    files = {
        "bom": outdir / f"{name}-bom.csv",
        "cpl": outdir / f"{name}-cpl.csv",
        "edge_cuts": outdir / f"{name}-Edge_Cuts.gbr",
        "drill": outdir / f"{name}.drl",
        "manifest": outdir / f"{name}-manifest.json",
    }
    _write_bom(files["bom"], parts)
    _write_cpl(files["cpl"], parts)
    _write_edge_cuts(files["edge_cuts"], w_mm, h_mm)
    _write_drill(files["drill"], w_mm, h_mm)

    notes = [
        "Placement is a pre-routing PLACEHOLDER grid (sized by real part bodies); "
        "real coordinates come from layout — GAPS §4e.",
        "Copper layers are NOT emitted: routing is upstream and not done. Only the "
        "mechanical outline (Edge.Cuts) + drill are produced.",
    ]
    pkg = Package(name=name, outdir=outdir, parts=parts, board_mm=(w_mm, h_mm),
                  files={k: v for k, v in files.items()}, notes=notes)
    files["manifest"].write_text(json.dumps({
        "name": name,
        "board_mm": [round(w_mm, 2), round(h_mm, 2)],
        "parts": [{"refdes": p.refdes, "mpn": p.mpn, "lcsc": p.lcsc,
                   "footprint": p.footprint, "x_mm": round(p.x_mm, 3),
                   "y_mm": round(p.y_mm, 3)} for p in pkg.parts],
        "files": {k: v.name for k, v in files.items() if k != "manifest"},
        "notes": notes,
    }, indent=2) + "\n", encoding="utf-8")
    return pkg


# ---- validate (reads the EMITTED files, not just memory) ---------------------
def validate_package(pkg: Package, snapshot: dict) -> list[str]:
    problems: list[str] = []
    for key, path in pkg.files.items():
        if not path.exists() or path.stat().st_size == 0:
            problems.append(f"file '{key}' missing or empty: {path.name}")
    if problems:
        return problems

    bom = list(csv.DictReader(pkg.files["bom"].open(encoding="utf-8")))
    cpl = list(csv.DictReader(pkg.files["cpl"].open(encoding="utf-8")))
    bom_refs = {r["Designator"] for r in bom}
    cpl_refs = {r["Designator"] for r in cpl}

    if bom_refs != cpl_refs:
        problems.append(f"BOM/CPL designator mismatch: BOM-only={bom_refs - cpl_refs}, "
                        f"CPL-only={cpl_refs - bom_refs}")
    for r in bom:
        lcsc = r["LCSC Part #"]
        gt = snapshot.get(lcsc)
        if gt is None:
            problems.append(f"{r['Designator']}: LCSC {lcsc!r} not in ground-truth snapshot")
        elif gt.stock is not None and gt.stock <= 0:
            problems.append(f"{r['Designator']}: LCSC {lcsc} is out of stock (not orderable)")

    gerber = pkg.files["edge_cuts"].read_text(encoding="utf-8")
    if "%FSLA" not in gerber or "%MOMM*%" not in gerber or not gerber.rstrip().endswith("M02*"):
        problems.append("Edge.Cuts gerber is not structurally valid RS-274X")
    drill = pkg.files["drill"].read_text(encoding="utf-8")
    if not drill.startswith("M48") or "M30" not in drill:
        problems.append("drill file is not a structurally valid Excellon program")
    return problems


# ---- dry-run JLCPCB order -----------------------------------------------------
def build_jlcpcb_order(pkg: Package, *, qty: int = 5, layers: int = 2) -> dict:
    """Assemble the JLCPCB assembly-order request. DRY-RUN: never submitted here —
    a real order needs JLCPCB API credentials and is a paid transaction."""
    return {
        "submit": False,                       # explicit: this spike does not place orders
        "endpoint": "https://jlcpcb.com/api/overseas-shop-cart/v1/shopCart/quoteAssembly",
        "method": "POST",
        "pcb": {"layers": layers, "size_mm": [round(pkg.board_mm[0], 2), round(pkg.board_mm[1], 2)],
                "quantity": qty, "material": "FR-4", "thickness_mm": 1.6},
        "assembly": {"side": "top", "tooling_holes": True,
                     "parts": [{"lcsc": p.lcsc, "designator": p.refdes, "qty": 1}
                               for p in pkg.parts]},
        "files": {"gerber": pkg.files["edge_cuts"].name, "drill": pkg.files["drill"].name,
                  "bom": pkg.files["bom"].name, "cpl": pkg.files["cpl"].name},
    }


# ---- routed package: real copper from the routed board (SPEC-ROUTING.md §5) ----
def _parse_routed_board(text: str) -> list[dict]:
    """Pull per-footprint BOM+placement out of a routed .kicad_pcb. The routed board
    is the single source of truth for both BOM and CPL (replacing the slice-derived
    placeholder). Each dict: ref, lcsc, value, footprint, x, y, rot, layer."""
    import place
    out = []
    for s, e in place._iter_footprint_blocks(text):
        b = text[s:e]
        def grab(pat, d=""):
            m = re.search(pat, b)
            return m.group(1) if m else d
        at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)", b)
        out.append({
            "ref": grab(r'\(property "Reference" "([^"]+)"'),
            "lcsc": grab(r'\(property "LCSC" "([^"]+)"'),
            "value": grab(r'\(property "Value" "([^"]+)"'),
            "footprint": grab(r'\(footprint "([^"]+)"').split(":")[-1],
            "x": float(at.group(1)) if at else 0.0,
            "y": float(at.group(2)) if at else 0.0,
            "rot": float(at.group(3)) if (at and at.group(3)) else 0.0,
            "layer": "bottom" if re.search(r'\(layer "B\.Cu"\)', b) else "top",
        })
    return out


def build_routed_package(routed_pcb: Path, gerbers_dir: Path, snapshot: dict,
                         outdir: Path, name: str = "verified") -> dict:
    """Assemble a JLCPCB package around the REAL routed board + kicad-cli Gerbers.
    BOM + CPL both come from the routed board; the copper/drill are the real exported
    files (no hand-rolled outline). Returns the package descriptor."""
    outdir.mkdir(parents=True, exist_ok=True)
    parts = _parse_routed_board(routed_pcb.read_text(encoding="utf-8"))

    bom = outdir / f"{name}-bom.csv"
    with bom.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for p in parts:
            w.writerow([p["value"], p["ref"], p["footprint"], p["lcsc"]])

    cpl = outdir / f"{name}-cpl.csv"
    with cpl.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in parts:
            w.writerow([p["ref"], f'{p["x"]:.3f}mm', f'{p["y"]:.3f}mm', p["layer"], p["rot"]])

    gdir = outdir / "gerbers"
    gdir.mkdir(exist_ok=True)
    copied = []
    for g in sorted(p for p in gerbers_dir.iterdir() if p.is_file()):
        (gdir / g.name).write_bytes(g.read_bytes())
        copied.append(g.name)

    return {"name": name, "parts": parts, "bom": bom, "cpl": cpl,
            "gerbers": copied, "gerbers_dir": gdir}


def validate_routed_package(pkg: dict, snapshot: dict) -> list[str]:
    """Gate the routed package: required copper layers present, no blank LCSC, no
    duplicate designators. Un-snapshotted passives (atopile-picked) are reported, not
    blessed (SPEC-ROUTING.md §5) — the snapshot does not pin the build's part-pick."""
    import route
    problems = []
    layers = route.gerber_layers_present(pkg["gerbers"])
    missing = route.REQUIRED_LAYERS - layers
    if missing:
        problems.append(f"missing copper layers {sorted(missing)} (have {sorted(layers)})")

    refs = [p["ref"] for p in pkg["parts"]]
    if len(refs) != len(set(refs)):
        problems.append(f"duplicate designators in {refs}")
    blank = [p["ref"] for p in pkg["parts"] if not p["lcsc"]]
    if blank:
        problems.append(f"parts with no LCSC code: {blank}")

    verified = [p["ref"] for p in pkg["parts"] if p["lcsc"] in snapshot]
    unsnap = [f'{p["ref"]}={p["lcsc"]}' for p in pkg["parts"]
              if p["lcsc"] and p["lcsc"] not in snapshot]
    print(f"  BOM: {len(pkg['parts'])} parts, {len(verified)} ground-truth-verified "
          f"({sorted(verified)}); un-snapshotted (atopile-picked, reported not blessed): {unsnap}")
    return problems


# ---- self-test ----------------------------------------------------------------
def selftest() -> bool:
    blocks = block_contract.load_blocks()
    snapshot = partdb.load_snapshot()
    slice_doc = _load_slice()
    ok = True
    print("fab-export self-test\n" + "-" * 70)

    with tempfile.TemporaryDirectory() as d:
        pkg = build_package(slice_doc, blocks, snapshot, Path(d) / "good")
        problems = validate_package(pkg, snapshot)
        good_ok = not problems
        ok &= good_ok
        print(f"  [{'ok' if good_ok else 'FAIL'}] sensor_node package: "
              f"{len(pkg.parts)} parts, board {pkg.board_mm[0]:.1f}×{pkg.board_mm[1]:.1f}mm, "
              f"{len(pkg.files)} files")
        for p in problems:
            print(f"        ✗ {p}")

        order = build_jlcpcb_order(pkg)
        order_ok = order["submit"] is False and len(order["assembly"]["parts"]) == len(pkg.parts)
        ok &= order_ok
        print(f"  [{'ok' if order_ok else 'FAIL'}] dry-run JLCPCB order: "
              f"{len(order['assembly']['parts'])} parts, submit={order['submit']}")

        # negative: a bogus LCSC must be rejected by validation
        bad_blocks = block_contract.load_blocks()
        bad_blocks["sensor_eeprom_24c256"].bound_part["lcsc"] = "C0000000"
        badpkg = build_package(slice_doc, bad_blocks, snapshot, Path(d) / "bad")
        bad_problems = validate_package(badpkg, snapshot)
        bad_ok = any("not in ground-truth snapshot" in p for p in bad_problems)
        ok &= bad_ok
        print(f"  [{'caught' if bad_ok else 'MISSED'}] bogus LCSC in a block -> "
              f"package rejected ({len(bad_problems)} problem(s))")

    print("-" * 70)
    print("SELFTEST:", "PASS — fab package built, validated, order assembled (dry-run)"
          if ok else "FAIL")
    return ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)

    out = HERE / "build" / "fab"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    blocks = block_contract.load_blocks()
    snapshot = partdb.load_snapshot()
    slice_doc = _load_slice()
    pkg = build_package(slice_doc, blocks, snapshot, out)
    problems = validate_package(pkg, snapshot)
    print(f"wrote {len(pkg.files)} files to {out}/  (board {pkg.board_mm[0]:.1f}×{pkg.board_mm[1]:.1f}mm)")
    for k, v in pkg.files.items():
        print(f"  · {v.name}")
    print("validation:", "PASS" if not problems else "FAIL")
    for p in problems:
        print(f"  ✗ {p}")
    print(json.dumps(build_jlcpcb_order(pkg), indent=2))
    raise SystemExit(0 if not problems else 1)
