"""Specctra DSN export + SES import via pcbnew (SPEC-ROUTING.md §4).

`kicad-cli` (KiCad 9) has NO Specctra path — `kicad-cli pcb export` lists no
`specctradsn`, and there is no SES importer. So the DSN→freerouting→SES round-trip
goes through `pcbnew` directly. pcbnew only installs against KiCad's SYSTEM python
(not the 3.13 venv), so route.py invokes this with `/usr/bin/python3`.

Confirmed signatures (KiCad 9.0.9, via the Task-4 probe):
    pcbnew.ExportSpecctraDSN(BOARD, wxString) -> bool
    pcbnew.ImportSpecctraSES(BOARD, wxString) -> bool

Usage:
    /usr/bin/python3 kicad_specctra.py export-dsn IN.kicad_pcb OUT.dsn
    /usr/bin/python3 kicad_specctra.py import-ses IN.kicad_pcb IN.ses OUT.kicad_pcb
"""
import sys

import pcbnew


def export_dsn(in_pcb: str, out_dsn: str) -> None:
    board = pcbnew.LoadBoard(in_pcb)
    if not pcbnew.ExportSpecctraDSN(board, out_dsn):
        raise SystemExit(f"ExportSpecctraDSN failed: {in_pcb} -> {out_dsn}")


def import_ses(in_pcb: str, in_ses: str, out_pcb: str) -> None:
    board = pcbnew.LoadBoard(in_pcb)
    if not pcbnew.ImportSpecctraSES(board, in_ses):
        raise SystemExit(f"ImportSpecctraSES failed: {in_ses} -> {in_pcb}")
    if not pcbnew.SaveBoard(out_pcb, board):
        raise SystemExit(f"SaveBoard failed: {out_pcb}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export-dsn":
        export_dsn(sys.argv[2], sys.argv[3])
    elif cmd == "import-ses":
        import_ses(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(f"usage: kicad_specctra.py export-dsn|import-ses ... (got {cmd!r})")
    print(f"{cmd} ok")
