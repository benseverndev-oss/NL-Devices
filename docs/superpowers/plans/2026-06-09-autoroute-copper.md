# Autoroute → Routed Copper Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a genuinely routed, DRC-clean `sensor_node` board with real copper Gerbers, exported to fab — closing `GAPS.md §4e`'s routing 🔴 for one vertical.

**Architecture:** New stage chain run in CI: `ato build` → `place.py` (pure placement into the `.kicad_pcb`) → Specctra DSN round-trip + headless **freerouting** → `kicad-cli` DRC + Gerber/drill export → `fab_export.py` assembles the JLCPCB package around the real copper. Pure logic (placement math, output parsing) is offline-testable via `--selftest`; tool invocations only run in CI.

**Tech Stack:** Python 3.13 (stdlib only — s-expression text manipulation, no pcbnew dependency in `place.py`), atopile 0.12.5, KiCad 9 (`kicad-cli` + `pcbnew` python for the Specctra round-trip), freerouting (Java, headless), GitHub Actions.

---

## ⚠️ Execution model — READ FIRST

**Do NOT run anything locally. Ben's machine OOMs on local installs/builds.** ([[offload-compute-not-local]])

- Local actions allowed: **edits, reads, greps only** (Write/Edit/Read/Grep/Glob).
- **All execution happens on GitHub runners (CI).** The test runner is CI, not local pytest.
- This project does **not** use pytest. Tests are `--selftest` functions inside each module that self-assert and `raise SystemExit(0|1)`, gated by CI steps. Match that convention — do not introduce pytest.
- The repo's `gh` account reverts between shells. Every `gh`/push command must start with `gh auth switch --user benzsevern >/dev/null 2>&1`. Push via the embedded-token URL ([[github-account-for-nl-devices]]).

**The canonical "run the test" step throughout this plan is:**

```bash
gh auth switch --user benzsevern >/dev/null 2>&1
TOKEN=$(gh auth token)
git push "https://x-access-token:${TOKEN}@github.com/benseverndev-oss/NL-Devices.git" feat/autoroute-copper:feat/autoroute-copper
gh run watch "$(gh run list --branch feat/autoroute-copper --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

`--exit-status` makes the command fail if CI fails, so a subagent can detect pass/fail. When the expensive `route` job fails, debug by downloading its artifacts:

```bash
gh run download <run-id> --name route-artifacts   # the .dsn/.ses/routed .kicad_pcb/DRC report/gerbers
```

**Branch:** `feat/autoroute-copper` (already on clean trunk `e8717f5`). Commit per task; push to verify. Do not open the final PR until the whole plan is green (Task 8).

**Cost discipline:** the `route` job is heavy (KiCad install + `ato build` network part-pick + freerouting). Develop Tasks 2–3 against the **offline `spike` job** first (fast), and only iterate the `route` job in Tasks 1, 4, 5, 8. Don't push the route job on every micro-step.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `spike/place.py` | **Create** | Pure deterministic placement. Parse footprints out of an unrouted `.kicad_pcb` (s-expr), place them courtyard-safe with decoupling caps near their owner, write `(at x y rot)` back. No KiCad dependency → offline-testable. |
| `spike/route.py` | **Create** | Tool orchestration (thin wrappers: `ato build`, DSN export, freerouting, SES import, DRC, Gerber export) **plus pure parsers** (`parse_unrouted`, `parse_drc`, `gerber_layers_present`). Parsers offline-testable; wrappers CI-only. |
| `spike/scripts/kicad_specctra.py` | **Create** | Tiny `pcbnew`-python helper for the Specctra DSN export + SES import round-trip (the one step `kicad-cli` may not cover). CI-only. |
| `spike/fixtures/sensor_node/` | **Create** | Captured `ato build` output (`sensor_node.kicad_pcb`, unrouted) + hand-authored parser samples (`freerouting.log`, `drc.json`, `gerbers.txt`). The offline test inputs. |
| `spike/fab_export.py` | **Modify** | Drop hand-rolled `_write_edge_cuts`/`_write_drill`; ingest `kicad-cli` Gerber/drill + routed CPL from the routed board; `--selftest` asserts copper layers present. |
| `.github/workflows/ci.yml` | **Modify** | Add `place.py`/`route.py` `--selftest` to the `spike` job; add the new isolated `route` job. |
| `scripts/check_toolchain.py` | **Modify** | Add `KICAD_VERSION` + `FREEROUTING_VERSION` constants; lint them against the `route` job's install pins. |
| `DESIGN.md` | **Modify** | §4 autoroute ⛔ AVOID → 🔨 BUILD (qualified), with the Quilter-swap-in rationale. |
| `GAPS.md` | **Modify** | §4e/§5.7: routing 🔴 closed for `sensor_node`. |
| `README.md` | **Modify** | Add `SPEC-ROUTING.md` to the doc list. |

---

## Task 1: Stand up the `route` CI job skeleton + capture the board fixture

**Why first:** every offline test in Tasks 2–3 needs a real unrouted `.kicad_pcb` to run against, and that can only come from `ato build` in CI. This task also de-risks the heavy-tool install (KiCad/Java/freerouting) and **probes** what `kicad-cli` actually exposes before we depend on it.

**Files:**
- Modify: `scripts/check_toolchain.py:17-18` (add pins)
- Modify: `.github/workflows/ci.yml` (add `route` job)
- Create: `spike/fixtures/sensor_node/` (committed after the run)

- [ ] **Step 1: Add the version pins to `check_toolchain.py`**

After line 18 (`PYTHON_VERSION = "3.13"`), add:

```python
KICAD_VERSION = "9.0"          # kicad-cli + pcbnew for the routing pipeline (route job)
FREEROUTING_VERSION = "2.1.0"  # headless autorouter, pinned by release tag
```

Add a lint block inside `main()` (after the setup-scripts loop, before the `print("-" * 72)`):

```python
    # routing toolchain pins must match what the `route` CI job installs
    ci = _read(".github/workflows/ci.yml")
    results.append(_check(f"ci.yml route job pins KiCad {KICAD_VERSION}",
                          f"kicad/kicad-{KICAD_VERSION}-releases" in ci, "PPA pin"))
    results.append(_check(f"ci.yml route job pins freerouting {FREEROUTING_VERSION}",
                          f"v{FREEROUTING_VERSION}/freerouting-{FREEROUTING_VERSION}.jar" in ci, "release pin"))
```

- [ ] **Step 2: Add the `route` job skeleton to `ci.yml`**

Append after the `toolchain` job:

```yaml
  route:
    name: Autoroute → routed copper (sensor_node)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - name: Install pinned atopile toolchain
        run: bash scripts/setup.sh
      - name: Install KiCad 9 + Java (route backend)
        run: |
          sudo add-apt-repository --yes ppa:kicad/kicad-9.0-releases
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends kicad default-jre
          kicad-cli version
      - name: PROBE kicad-cli capabilities (Task 1 — learn the surface)
        run: |
          echo "== pcb export ==" ; kicad-cli pcb export --help || true
          echo "== pcb drc ==" ;   kicad-cli pcb drc --help || true
          python3 -c "import pcbnew; print('pcbnew', pcbnew.GetBuildVersion()); print([a for a in dir(pcbnew) if 'pecctra' in a or 'SES' in a or 'DSN' in a])"
      - name: Fetch pinned freerouting
        run: |
          curl -fL -o freerouting.jar \
            "https://github.com/freerouting/freerouting/releases/download/v2.1.0/freerouting-2.1.0.jar"
          java -jar freerouting.jar --version || java -jar freerouting.jar -h || true
      - name: ato build sensor_node (network part-pick — the fragile step)
        working-directory: spike/atopile
        run: |
          ato build sensor_node
          echo "== located boards ==" ; find . -name '*.kicad_pcb'
      - name: Upload unrouted board as fixture
        uses: actions/upload-artifact@v4
        with:
          name: sensor_node-unrouted
          path: spike/atopile/**/*.kicad_pcb
          if-no-files-found: error
```

- [ ] **Step 3: Commit + push + watch CI** (canonical verify step above).
  Expected: the `route` job reaches "Upload unrouted board" green. Read the **PROBE** step log — record whether `kicad-cli pcb export` lists `specctradsn`/`pos`, and whether `pcbnew` exposes `ExportSpecctra*`/`ImportSpecctraSES*`. This decides Task 4's round-trip path. The `spike`/`toolchain` jobs are unaffected.

- [ ] **Step 4: Download the fixture and commit it**

```bash
gh auth switch --user benzsevern >/dev/null 2>&1
RUN=$(gh run list --branch feat/autoroute-copper --limit 1 --json databaseId --jq '.[0].databaseId')
gh run download "$RUN" --name sensor_node-unrouted --dir /tmp/board
# copy the single .kicad_pcb into the fixture dir, normalized name
mkdir -p spike/fixtures/sensor_node
cp "$(find /tmp/board -name '*.kicad_pcb' | head -1)" spike/fixtures/sensor_node/sensor_node.kicad_pcb
git add spike/fixtures/sensor_node/sensor_node.kicad_pcb scripts/check_toolchain.py .github/workflows/ci.yml
git commit -m "Stand up route CI job + capture unrouted sensor_node fixture"
```

> Note: `spike/.gitignore` ignores `**/elec/layout/` and `build/` — that's why the board isn't already committed. The fixture under `spike/fixtures/` is a deliberate, tracked copy. Regenerate it (re-run this task) whenever the blocks change; the live `ato build` in the `route` job is what catches drift.

---

## Task 2: `place.py` — pure deterministic placement (offline `--selftest`)

**Files:**
- Create: `spike/place.py`
- Test input: `spike/fixtures/sensor_node/sensor_node.kicad_pcb` (from Task 1)
- Modify: `.github/workflows/ci.yml` (add to `spike` job)

Use @superpowers:test-driven-development: write the `--selftest` assertions first, watch them fail in CI, then implement.

- [ ] **Step 1: Write `place.py` with the selftest skeleton first**

Create `spike/place.py`. Start with the data model + a failing `selftest()` that asserts the contract, and stubs that raise:

```python
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
FIXTURE = HERE / "fixtures" / "sensor_node" / "sensor_node.kicad_pcb"
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
```

- [ ] **Step 2: Implement the s-expr footprint scanner**

Add a paren-depth scanner that finds each top-level `(footprint ...)` block, its reference designator (`(property "Reference" "U1" ...)` or `(fp_text reference U1 ...)`), its `(at ...)` span, and a body size. Prefer the courtyard bbox (`(fp_poly ... (layer "F.CrtYd"))` / `F.CrtYd` lines) for body size; fall back to parsing the footprint library id's `L#-W#` token (same regex as `fab_export._body_dims`), else 5×5.

```python
_REF_RE = re.compile(r'\(property "Reference" "([^"]+)"|\(fp_text reference (\S+)')
_AT_RE = re.compile(r"\(at [^)]*\)")
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
```

> If the PROBE in Task 1 shows footprint refs live in a different node, adjust `_REF_RE` against the fixture text (read `spike/fixtures/sensor_node/sensor_node.kicad_pcb` directly — it's committed). This is the most fixture-dependent regex; verify it by eye before relying on it.

- [ ] **Step 3: Implement courtyard-safe placement**

Grid place by descending body size (big ICs first), pitch = max courtyard + `SPACING_MM`; then nudge each decoupling cap (`ref` starts with `C`, small body) toward the nearest large IC if room allows. Keep it deterministic (stable sort, no RNG). Return board WxH.

```python
def place(fps: list[FP]) -> tuple[float, float]:
    order = sorted(fps, key=lambda p: -max(p.body_mm))
    pitch = max((max(p.body_mm) for p in fps), default=5.0) + SPACING_MM
    cols = max(1, math.ceil(math.sqrt(len(fps))))
    for idx, p in enumerate(order):
        col, row = idx % cols, idx // cols
        p.x = MARGIN_MM + col * pitch + max(p.body_mm) / 2
        p.y = MARGIN_MM + row * pitch + max(p.body_mm) / 2
    rows = math.ceil(len(fps) / cols)
    return (2 * MARGIN_MM + cols * pitch, 2 * MARGIN_MM + rows * pitch)
```

- [ ] **Step 4: Implement the writer (rewrite each `(at ...)`, back-to-front)**

```python
def write_positions(text: str, fps: list[FP]) -> str:
    for p in sorted(fps, key=lambda p: -p.at_span[0]):   # back-to-front keeps spans valid
        a, b = p.at_span
        text = text[:a] + f"(at {p.x:.4f} {p.y:.4f} {p.rot})" + text[b:]
    return text
```

- [ ] **Step 5: Implement `selftest()` — the contract**

```python
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
    print(f"  [{'ok' if not overlap else 'FAIL'}] no courtyard overlap (board {w:.1f}×{h:.1f}mm)"); ok &= not overlap
    for r in overlap: print(f"        ✗ {r[0]} ~ {r[1]}")
    out = write_positions(text, fps)
    det = write_positions(text, parse_footprints(text)) == out and out.count("(footprint") == text.count("(footprint")
    print(f"  [{'ok' if det else 'FAIL'}] writer deterministic + footprint count preserved"); ok &= det
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
```

- [ ] **Step 6: Wire into the `spike` job**

In `ci.yml`, under the `spike` job's "Validator + contract + …" step, add a line:

```yaml
          python3 place.py --selftest    # pure placement, against committed fixture
```

- [ ] **Step 7: Commit + push + watch CI.** Expected: `spike` job green, `place self-test … PASS`. Iterate the regexes against the fixture text if parse fails — purely by editing (no local runs).

---

## Task 3: `route.py` parsers — pure, offline `--selftest`

**Files:**
- Create: `spike/route.py` (parsers section only this task)
- Create: `spike/fixtures/sensor_node/freerouting.log`, `drc.json`, `gerbers.txt` (hand-authored samples)
- Modify: `.github/workflows/ci.yml` (`spike` job)

- [ ] **Step 1: Hand-author the parser fixtures** (cheap text — author by hand, no tools)

`spike/fixtures/sensor_node/drc.json` — a minimal KiCad DRC JSON with **zero** violations (the success shape) plus a sibling note. Use the real KiCad schema discovered in Task 1's PROBE if it differs:

```json
{ "$schema": "kicad-drc", "source": "sensor_node.kicad_pcb",
  "violations": [], "unconnected_items": [], "schematic_parity": [],
  "coordinate_units": "mm" }
```

`spike/fixtures/sensor_node/freerouting.log` — a few lines incl. the completion summary freerouting prints, e.g. a line containing `Routing ... 100% ... incomplete: 0` (adjust to the real string seen in Task 4's first run; for now encode the success and a failure sample as two files `freerouting.ok.log` / `freerouting.bad.log`).

`spike/fixtures/sensor_node/gerbers.txt` — the expected Gerber file list (one per line: `*-F_Cu.gbr`, `*-B_Cu.gbr`, `*-F_Mask.gbr`, …, `*-Edge_Cuts.gbr`, `*.drl`).

- [ ] **Step 2: Write `route.py` parsers + failing selftest**

```python
"""Routing pipeline orchestration + pure output parsers (SPEC-ROUTING.md §3).

The tool wrappers (ato/kicad-cli/freerouting) only run in CI; the PARSERS here are
pure and tested offline against fixtures, so a regression in 'did it route / is it
DRC-clean / are the copper layers present' is caught without the heavy toolchain.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE / "fixtures" / "sensor_node"

def parse_unrouted(freerouting_log: str) -> int:
    """Return the count of unrouted/incomplete connections freerouting reports.
    Looks for 'incomplete: N' (or 'N incomplete' / 'unrouted: N'). Raises if absent."""
    for pat in (r"incomplete[:\s]+(\d+)", r"(\d+)\s+incomplete", r"unrouted[:\s]+(\d+)"):
        m = re.search(pat, freerouting_log, re.I)
        if m:
            return int(m.group(1))
    raise ValueError("no completion summary found in freerouting log")

def parse_drc(drc_json: str) -> list[dict]:
    """Return the list of error-severity DRC violations from kicad-cli JSON."""
    doc = json.loads(drc_json)
    out = []
    for v in doc.get("violations", []):
        if v.get("severity", "error") == "error":
            out.append(v)
    return out

def gerber_layers_present(names: list[str]) -> set[str]:
    """Classify a list of exported file names into the layers we require."""
    want = {"F_Cu": r"F_Cu", "B_Cu": r"B_Cu", "Edge_Cuts": r"Edge_Cuts", "drill": r"\.drl$"}
    return {k for k, pat in want.items() if any(re.search(pat, n) for n in names)}

REQUIRED_LAYERS = {"F_Cu", "B_Cu", "Edge_Cuts", "drill"}

def selftest() -> bool:
    ok = True; print("route parsers self-test\n" + "-" * 60)
    u0 = parse_unrouted((FIX / "freerouting.ok.log").read_text())
    print(f"  [{'ok' if u0 == 0 else 'FAIL'}] ok log -> 0 unrouted"); ok &= (u0 == 0)
    ub = parse_unrouted((FIX / "freerouting.bad.log").read_text())
    print(f"  [{'ok' if ub > 0 else 'FAIL'}] bad log -> {ub} unrouted (>0)"); ok &= (ub > 0)
    v = parse_drc((FIX / "drc.json").read_text())
    print(f"  [{'ok' if v == [] else 'FAIL'}] clean drc.json -> 0 violations"); ok &= (v == [])
    names = (FIX / "gerbers.txt").read_text().split()
    present = gerber_layers_present(names)
    full = REQUIRED_LAYERS <= present
    print(f"  [{'ok' if full else 'FAIL'}] gerber set has required layers {sorted(present)}"); ok &= full
    print("-" * 60); print("SELFTEST:", "PASS" if ok else "FAIL"); return ok

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    if "--selftest" in sys.argv:
        raise SystemExit(0 if selftest() else 1)
    # full pipeline entrypoint added in Task 4
    raise SystemExit("route.py: pipeline mode not yet implemented (Task 4)")
```

- [ ] **Step 3: Add `python3 route.py --selftest` to the `spike` job** (next to `place.py`).

- [ ] **Step 4: Commit + push + watch CI.** Expected: `spike` job green, `route parsers self-test … PASS`.

---

## Task 4: `route.py` pipeline + grow the `route` job to full autoroute

**This is the expensive, iterative task.** Expect several `route`-job CI rounds to nail headless DSN/SES + freerouting flags + a DRC-clean result. Debug via `gh run download`.

**Files:**
- Modify: `spike/route.py` (add tool wrappers + `pipeline()`)
- Create: `spike/scripts/kicad_specctra.py` (pcbnew round-trip helper)
- Modify: `.github/workflows/ci.yml` (`route` job → full pipeline + artifact upload + hard gate)

- [ ] **Step 1: Write `spike/scripts/kicad_specctra.py`** — a pcbnew helper exposing two subcommands, `export-dsn IN.kicad_pcb OUT.dsn` and `import-ses IN.kicad_pcb IN.ses OUT.kicad_pcb`, using whichever pcbnew API the Task 1 PROBE confirmed (`ExportSpecctraDSN`/`ImportSpecctraSES` family). This isolates the one uncertain tool call. If the PROBE showed `kicad-cli pcb export specctradsn` exists, prefer that in `route.py` and keep this helper only for the SES import.

- [ ] **Step 2: Add the tool wrappers to `route.py`**

Add `subprocess`-based wrappers, each asserting `returncode == 0` and returning captured stdout:

```python
import subprocess
NET_CLASS_TRACK_MM = 0.2
NET_CLASS_CLEAR_MM = 0.2

def _run(cmd, **kw) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({p.returncode}):\n{p.stderr[-2000:]}")
    return p.stdout

def ato_build(atodir: Path) -> Path: ...      # `ato build sensor_node`; return the .kicad_pcb path
def set_netclass(pcb: Path) -> None: ...       # ensure a default net class @ 0.2/0.2 + via, so DRC==freerouting rules
def export_dsn(pcb: Path, dsn: Path) -> None: ...
def run_freerouting(dsn: Path, ses: Path) -> str: ...   # `java -jar freerouting.jar -de DSN -do SES`; return log
def import_ses(pcb: Path, ses: Path, out: Path) -> None: ...
def run_drc(pcb: Path, out_json: Path) -> str: ...      # `kicad-cli pcb drc --format json --exit-code-violations`
def export_gerbers(pcb: Path, outdir: Path) -> list[str]: ...  # gerbers + drill; return file names
```

> **DRC-clean-by-construction (SPEC §4):** `set_netclass` must write the **same** track width / clearance the DSN carries into freerouting, so the routed result passes `kicad-cli pcb drc`. The freerouting flags (`-de`/`-do` vs `--input`/`--output`) are confirmed against the pinned 2.1.0 jar in the first CI run — adjust `run_freerouting` to match the PROBE/`-h` output.

- [ ] **Step 3: Add the `pipeline()` entrypoint with the hard gate**

```python
def pipeline(atodir: Path, workdir: Path) -> int:
    import place
    pcb = ato_build(atodir)
    placed = workdir / "placed.kicad_pcb"
    placed.write_text(place.write_positions(pcb.read_text(),
                      (lambda t: (place.place(fps := place.parse_footprints(t)) , fps)[1])(pcb.read_text())))
    set_netclass(placed)
    dsn, ses, routed = workdir / "b.dsn", workdir / "b.ses", workdir / "routed.kicad_pcb"
    export_dsn(placed, dsn)
    log = run_freerouting(dsn, ses); (workdir / "freerouting.log").write_text(log)
    unrouted = parse_unrouted(log)
    import_ses(placed, ses, routed)
    drc_json = run_drc(routed, workdir / "drc.json")
    violations = parse_drc(drc_json)
    names = export_gerbers(routed, workdir / "gerbers")
    layers = gerber_layers_present(names)
    ok = unrouted == 0 and not violations and REQUIRED_LAYERS <= layers
    print(f"unrouted={unrouted}  drc_violations={len(violations)}  layers={sorted(layers)}")
    return 0 if ok else 1
```

(Refactor the inline lambda into a clean `place_board(pcb)` helper in `place.py` — DRY.)

- [ ] **Step 4: Grow the `route` job** — replace Task 1's "Upload unrouted board" tail with the full pipeline + artifact upload, hard-gating on the pipeline exit code:

```yaml
      - name: Route + DRC + export copper (HARD GATE: 0 unrouted, 0 DRC)
        working-directory: spike
        run: python3 route.py --pipeline --atodir atopile --work build/route
      - name: Upload route artifacts (always, for debugging)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: route-artifacts
          path: spike/build/route/**
```

- [ ] **Step 5: Commit + push + watch the `route` job.** Iterate: download `route-artifacts`, inspect `freerouting.log`/`drc.json`, fix flags/netclass/placement, repeat until `unrouted=0 drc_violations=0`. **Update the Task 3 hand-authored `freerouting.ok.log`/`drc.json` fixtures to match the real strings** once seen, so the offline parser tests track reality.

---

## Task 5: Fold real copper into `fab_export.py`

**Files:**
- Modify: `spike/fab_export.py` (`build_package`, `validate_package`, `build_jlcpcb_order`, `selftest`, delete `_write_edge_cuts`/`_write_drill`/`place_parts`)
- Modify: `.github/workflows/ci.yml` (`route` job: call `fab_export` after the pipeline)

- [ ] **Step 1: Add a "routed package" mode to `build_package`** that, given the routed board's `kicad-cli` Gerber/drill output dir + the routed CPL (footprint positions read back from the routed `.kicad_pcb` via `place.parse_footprints`), assembles the package using the **real** copper files instead of `_write_edge_cuts`/`_write_drill`. Keep the BOM from the `verify_parts` snapshot for bound ICs; generate CPL for **every** placed footprint (incl. passives).

- [ ] **Step 2: Implement the §5 BOM/CPL reconciliation** in `validate_package`: assert `bom_refs ⊆ cpl_refs` (was `==`; now BOM is IC-only, CPL is all footprints), every bound IC reconciles to the snapshot, and **report** (don't fail on) un-snapshotted passives. Replace the RS-274X/Excellon string checks with: assert the required copper layers (`F_Cu`, `B_Cu`, `Edge_Cuts`, drill) are present and non-empty.

- [ ] **Step 3: Update `selftest()`** to assert the package now carries copper layers + a routed CPL, while keeping the existing bogus-LCSC rejection. Since `selftest` can't route offline, it runs against a **committed routed fixture** (capture `spike/build/route/gerbers/` + routed board from Task 4's green run into `spike/fixtures/sensor_node/routed/`). Update the honesty `notes` (drop "copper not emitted").

- [ ] **Step 4: Wire `fab_export` into the `route` job** after the pipeline step:

```yaml
      - name: Assemble JLCPCB package with real copper
        working-directory: spike
        run: python3 fab_export.py --routed build/route --selftest
```

- [ ] **Step 5: Commit + push + watch both jobs.** Expected: `spike` job runs `fab_export.py --selftest` (offline, against the routed fixture) green; `route` job assembles the real-copper package green.

---

## Task 6: Docs + strategy reversal

**Files:** Modify `DESIGN.md`, `GAPS.md`, `README.md`.

- [ ] **Step 1: `DESIGN.md` §4** — move autorouting from the ⛔ AVOID table to a 🔨 BUILD (qualified) row, with the rationale verbatim from `SPEC-ROUTING.md §7` (own a reference freerouting path to make "routed PCB → fab" real for one vertical; Quilter swaps in at the `.dsn`/`.ses` seam; "complement, don't fight" holds). Leave a one-line note in the AVOID table pointing to the new row so the reversal is explicit, not silent.
- [ ] **Step 2: `GAPS.md` §4e + §5 item 7** — mark the routing 🔴 closed for `sensor_node`: genuinely routed, DRC-clean, real copper Gerbers via `route.py`/CI; keep the honest scope (one board, deterministic placement, network on CI path). Update the §4e severity marker.
- [ ] **Step 3: `README.md`** — add the `SPEC-ROUTING.md` bullet to the Docs list, matching the existing entries' style.
- [ ] **Step 4: Commit + push + watch.** Only offline gates run; expected green.

---

## Task 7: Full-plan verification + open the PR

- [ ] **Step 1:** Re-read `SPEC-ROUTING.md §8` acceptance criteria and confirm each is met by a green CI step (use @superpowers:verification-before-completion — evidence, not assertion). Map each criterion to the job/step that proves it.
- [ ] **Step 2:** Confirm the latest `feat/autoroute-copper` run has **all three jobs green** (`spike`, `toolchain`, `route`):
  ```bash
  gh auth switch --user benzsevern >/dev/null 2>&1
  gh run list --branch feat/autoroute-copper --limit 1
  ```
- [ ] **Step 3:** Push the branch (already done per task) and open the PR to trunk:
  ```bash
  gh auth switch --user benzsevern >/dev/null 2>&1
  gh pr create --base claude/brainstorm-idea-vegk59 --head feat/autoroute-copper \
    --title "Own the autoroute: routed copper → fab (closes GAPS §4e 🔴)" \
    --body "<summary + the DESIGN §4 reversal note + honest scope from SPEC-ROUTING.md>"
  ```
- [ ] **Step 4:** Watch PR checks green, then surface to Ben for review/merge (do **not** self-merge; per cadence Ben decides). Update [[nl-devices-project]] memory: autoroute landed, trunk tip, GAPS §4e closed.

---

## Notes / risks carried from the spec
- **Headless freerouting flags + kicad-cli Specctra support are confirmed in CI, not assumed** — Task 1 PROBE + Task 4 iteration own this. If `kicad-cli` lacks Specctra entirely, `spike/scripts/kicad_specctra.py` (pcbnew) covers both export + import.
- **DRC-clean depends on netclass==freerouting-rules** (Task 4 Step 2). If DRC fails on clearance, the fix is aligning `set_netclass` with the DSN rules, not loosening the gate.
- **If freerouting can't reach 0 unrouted** on the deterministic placement, tune `place.py` (Task 2) — bigger board / caps-near-pins — before touching the gate. The hard gate stays.
- **Network `ato build`** is the known-fragile CI step; it's isolated in the `route` job so the `spike`/`toolchain` gates stay deterministic and green independently.
