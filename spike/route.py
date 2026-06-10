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
    """Return the count of unrouted connections freerouting reports.

    freerouting 2.x emits an authoritative JSON `"incomplete_count": N` summary, plus
    per-pass `(N unrouted)` lines (dropped once it reaches 0). Prefer incomplete_count;
    fall back to the LAST per-pass count (a conservative over-estimate). Raises if neither.
    """
    m = re.search(r'"?incomplete_count"?\s*:\s*(\d+)', freerouting_log)
    if m:
        return int(m.group(1))
    passes = re.findall(r"\((\d+)\s+unrouted\)", freerouting_log, re.I)
    if passes:
        return int(passes[-1])
    for pat in (r"incomplete[:\s]+(\d+)", r"unrouted[:\s]+(\d+)"):
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
# Tool orchestration — CI only (shells out to pcbnew / freerouting / kicad-cli)
# ---------------------------------------------------------------------------

def _run(cmd: list, check: bool = True) -> str:
    """Run a command, echo it, return stdout+stderr. Raises on nonzero if check."""
    import subprocess
    cmd = [str(c) for c in cmd]
    print("+ " + " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    if out.strip():
        print(out[-4000:])
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed (exit {p.returncode})")
    return out


def export_dsn(specctra: str, in_pcb: str, out_dsn: str) -> None:
    # pcbnew lives in KiCad's system python, not the 3.13 venv → /usr/bin/python3.
    _run(["/usr/bin/python3", specctra, "export-dsn", in_pcb, out_dsn])


def run_freerouting(jar: str, dsn: str, ses: str) -> str:
    # freerouting 2.x runs headless in CLI mode when given both -de (input .dsn) and
    # -do (output .ses). -Djava.awt.headless avoids the GUI screen-resolution probe.
    return _run(["java", "-Djava.awt.headless=true", "-jar", jar,
                 "-de", dsn, "-do", ses, "-mp", "100"])


def import_ses(specctra: str, in_pcb: str, ses: str, out_pcb: str) -> None:
    _run(["/usr/bin/python3", specctra, "import-ses", in_pcb, ses, out_pcb])


def run_drc(routed_pcb: str, out_json: str) -> str:
    # --exit-code-violations returns nonzero when violations exist; that's expected
    # signal, not a tool failure, so check=False and let parse_drc be the truth.
    _run(["kicad-cli", "pcb", "drc", routed_pcb, "--format", "json",
          "--severity-error", "--exit-code-violations", "-o", out_json], check=False)
    return Path(out_json).read_text(encoding="utf-8")


def export_gerbers(routed_pcb: str, outdir: str) -> list[str]:
    Path(outdir).mkdir(parents=True, exist_ok=True)
    _run(["kicad-cli", "pcb", "export", "gerbers", "-o", outdir,
          "--layers", "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts", routed_pcb])
    _run(["kicad-cli", "pcb", "export", "drill", "-o", outdir, routed_pcb])
    return [p.name for p in Path(outdir).iterdir()]


def pipeline(board: str, jar: str, specctra: str, workdir: str) -> int:
    """ato-built board → place + outline → DSN → freerouting → SES → DRC → Gerbers.
    HARD GATE: 0 unrouted nets, 0 DRC violations, all REQUIRED_LAYERS present."""
    import place  # spike/ is on sys.path[0] when route.py is the entrypoint
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    # 1. place footprints courtyard-safe + stamp a board outline
    text = Path(board).read_text(encoding="utf-8")
    fps = place.parse_footprints(text)
    w, h = place.place(fps)
    placed_txt = place.add_outline(
        place.allow_mask_bridges(place.write_positions(text, fps)), w, h)
    placed = work / "placed.kicad_pcb"
    placed.write_text(placed_txt, encoding="utf-8")
    print(f"placed {len(fps)} footprints, board {w:.1f}x{h:.1f}mm -> {placed}")

    # 2. export Specctra DSN (pcbnew)
    dsn = work / "board.dsn"
    export_dsn(specctra, str(placed), str(dsn))

    # 3. autoroute (freerouting, headless)
    ses = work / "board.ses"
    log = run_freerouting(jar, str(dsn), str(ses))
    (work / "freerouting.log").write_text(log, encoding="utf-8")
    unrouted = parse_unrouted(log)

    # 4. import the routed session back into a board (pcbnew)
    routed = work / "routed.kicad_pcb"
    import_ses(specctra, str(placed), str(ses), str(routed))

    # 5. DRC on the routed board
    violations = parse_drc(run_drc(str(routed), str(work / "drc.json")))

    # 6. export real copper Gerbers + drill
    gdir = work / "gerbers"
    layers = gerber_layers_present(export_gerbers(str(routed), str(gdir)))

    # 7. assemble + validate the JLCPCB package around the real copper + routed CPL
    import fab_export
    import partdb
    snap = partdb.load_snapshot()
    pkg = fab_export.build_routed_package(routed, gdir, snap, work / "package")
    pkg_problems = fab_export.validate_routed_package(pkg, snap)
    for p in pkg_problems:
        print(f"   PKG: {p}")

    ok = (unrouted == 0 and not violations and REQUIRED_LAYERS <= layers
          and not pkg_problems)
    print(f"\n== GATE ==  unrouted={unrouted}  drc_violations={len(violations)}  "
          f"layers={sorted(layers)}  pkg_problems={len(pkg_problems)}  ->  {'PASS' if ok else 'FAIL'}")
    if violations:
        for v in violations[:10]:
            print(f"   DRC: {v.get('type', '?')} {v.get('description', '')}")
    return 0 if ok else 1


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

    if "--pipeline" in sys.argv:
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--pipeline", action="store_true")
        ap.add_argument("--board", required=True)
        ap.add_argument("--jar", required=True)
        ap.add_argument("--specctra", required=True)
        ap.add_argument("--work", default="build/route")
        a = ap.parse_args()
        raise SystemExit(pipeline(a.board, a.jar, a.specctra, a.work))

    raise SystemExit("route.py: use --selftest (offline parsers) or --pipeline (CI)")
