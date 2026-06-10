# STM32 core + netlist-equivalence guard — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a netlist-equivalence guard that proves a board's connectivity is unchanged, then use it to extract a shared `Stm32CoreBlock` as a provably-pure refactor.

**Architecture:** Two CI-gated workstreams, **guard-first**. WS1 adds `spike/netlist.py` (pure stdlib; reduces a built `.kicad_pcb` to a canonical, name/refdes-independent connectivity form), captures golden netlists for both boards, and makes the `route` job assert every build matches golden. WS2 extracts `Stm32CoreBlock` from the duplicated STM32 boilerplate in `McuBlock`/`McuSpiBlock`; the guard proves it's electrically inert.

**Tech Stack:** Python 3.13 stdlib (netlist.py — local + CI); atopile 0.12.5 + KiCad 9 + freerouting (boards — CI only).

---

## ⚠️ Execution constraints (read first)

- **NEVER run heavy compute locally — it OOMs the box.** No `ato build`, `pip install`, KiCad, or freerouting locally. **CI is the test runner** for anything board-related.
- **`spike/netlist.py` is pure stdlib** — run + test it locally: `python3 spike/netlist.py --selftest`. No `pip`.
- **The sandbox can't download CI artifacts or run `ato build`** — so golden netlists are produced **and committed by CI** (a one-shot job), then pulled. Same technique used for the committed part files.
- **Push** over the embedded-token URL (gh as `benzsevern`): `git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git <branch>`.
- **Cadence:** branch off trunk `claude/brainstorm-idea-vegk59` → CI green → `gh pr merge <n> --squash --delete-branch`.
- **WS2 must not change either board electrically** — the guard (WS1) is what proves it.

---

## File Structure

| File | WS | Responsibility | Action |
|------|----|----------------|--------|
| `spike/netlist.py` | 1 | Canonical netlist extractor + `--emit`/`--check`/`--selftest` | **Create** |
| `spike/fixtures/golden/verified.netlist.json` | 1 | Golden connectivity of the `verified` board | **Create** (in CI) |
| `spike/fixtures/golden/spi_node.netlist.json` | 1 | Golden connectivity of the `spi_node` board | **Create** (in CI) |
| `.github/workflows/ci.yml` | 1 | CI | **Modify** — `--selftest` in `spike`; one-shot golden job (added then removed); `--check` per board in `route` |
| `spike/atopile/verified_lib.ato` | 2 | Shared block lib | **Modify** — add `Stm32CoreBlock`; rewrite `McuBlock`/`McuSpiBlock` as thin wrappers |

---

# Workstream 1 — the netlist-equivalence guard

**Branch:** `feat/netlist-guard` (already exists; carries the spec).

### Task 1: `spike/netlist.py` (pure stdlib, local)

**Files:** Create `spike/netlist.py`

- [ ] **Step 1: Write the module.** Create `spike/netlist.py` with exactly this content:

```python
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
```

- [ ] **Step 2: Run the selftest (local).**

Run: `python3 spike/netlist.py --selftest`
Expected: **exit 0**, `SELFTEST: PASS` — all four lines ok (deterministic emit, parts/nets parsed from the committed fixture, JSON round-trip, change-is-detected).

- [ ] **Step 3: Eyeball an emit (local).**

Run: `python3 spike/netlist.py --emit spike/fixtures/verified/verified.kicad_pcb | head -20`
Expected: JSON with `"parts"` (e.g. `YAGEO_CC0603KRX7R9BB104:C0603|100nF ±10% 50V X7R`) and `"nets"` (lists of `libid|value|pad` members). No net names or refdes (C1/C2) appear.

- [ ] **Step 4: Commit.**

```bash
git add spike/netlist.py
git commit -m "Add netlist.py: canonical connectivity extractor (--emit/--check/--selftest)"
```

### Task 2: wire `--selftest` into the `spike` CI job

**Files:** Modify `.github/workflows/ci.yml`

- [ ] **Step 1:** In the `spike` job's "Validator + contract + orchestrator + planner eval" step (which already runs `place.py --selftest` / `route.py --selftest`), add a line:

```bash
          python3 netlist.py --selftest   # pure netlist extractor, against the committed fixture
```
(placed next to the other `--selftest` lines; `working-directory: spike` so the path is `netlist.py`).

- [ ] **Step 2: Commit + push + verify.**

```bash
git add .github/workflows/ci.yml
git commit -m "Run netlist.py --selftest in the spike CI job"
git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/netlist-guard -u
```
Watch the run (`gh run list --branch feat/netlist-guard --limit 1 --json databaseId -q '.[0].databaseId'` → `gh run watch <id> --exit-status`). Expected: `spike` job green, `netlist.py --selftest` PASS in the log.

### Task 3: capture golden netlists (one-shot CI job)

**Files:** Modify `.github/workflows/ci.yml` (add then remove a `make-golden` job); Create `spike/fixtures/golden/*.netlist.json` (via CI)

> CI must produce the goldens (the sandbox can't `ato build` or download artifacts). This is a temporary job that builds both boards, emits goldens, and commits them back.

- [ ] **Step 1: Add a one-shot `make-golden` job** to `ci.yml`. Mirror the `route` job's atopile-install steps (setup-python 3.13 + the pinned-atopile install), then:

```yaml
  make-golden:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install pinned atopile toolchain
        run: |
          # COPY the exact install step the `route` job uses (setup.sh or the pinned pip install)
          bash scripts/setup.sh
      - name: Build both boards + emit goldens
        run: |
          export PATH="$HOME/.local/bin:$PATH"
          ( cd spike/atopile && ato build -b verified && ato build -b spi_node )
          mkdir -p spike/fixtures/golden
          python3 spike/netlist.py --emit spike/atopile/elec/layout/verified/verified.kicad_pcb  > spike/fixtures/golden/verified.netlist.json
          python3 spike/netlist.py --emit spike/atopile/elec/layout/spi_node/spi_node.kicad_pcb > spike/fixtures/golden/spi_node.netlist.json
      - name: Commit goldens back
        run: |
          git config user.name benzsevern
          git config user.email benzsevern@gmail.com
          git add spike/fixtures/golden/
          git commit -m "Capture golden netlists for verified + spi_node [skip ci]" || echo "nothing to commit"
          git push
```

- [ ] **Step 2: Commit + push + watch.** Push; watch the `make-golden` job to green. It commits `spike/fixtures/golden/{verified,spi_node}.netlist.json` back to the branch with `[skip ci]`.
- [ ] **Step 3: Pull + sanity-check the goldens.**

```bash
git pull https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/netlist-guard
git ls-files spike/fixtures/golden/
python3 -c "import json; [print(f, len(json.load(open(f))['parts']),'parts',len(json.load(open(f))['nets']),'nets') for f in ['spike/fixtures/golden/verified.netlist.json','spike/fixtures/golden/spi_node.netlist.json']]"
```
Expected: both JSONs present; `verified` ≈ many parts incl. the STM32 (`STMicroelectronics_STM32F103C8T6:...`), `spi_node` incl. the STM32 + `Winbond_Elec_W25Q128JVSIQ:...`.

- [ ] **Step 4: Remove the one-shot `make-golden` job** from `ci.yml` (it has done its job). Commit.

```bash
git add .github/workflows/ci.yml
git commit -m "Remove one-shot golden-capture job (goldens committed)"
```

### Task 4: assert `--check` per board in the `route` job

**Files:** Modify `.github/workflows/ci.yml`

- [ ] **Step 1:** In the `route` job, **after each board's `ato build`** (the `verified` build step, and the `spi_node` build step), add a check against its golden:

```bash
          python3 spike/netlist.py --check spike/atopile/elec/layout/verified/verified.kicad_pcb  spike/fixtures/golden/verified.netlist.json
```
and for the SPI board:
```bash
          python3 spike/netlist.py --check spike/atopile/elec/layout/spi_node/spi_node.kicad_pcb spike/fixtures/golden/spi_node.netlist.json
```
(Run from the repo root — adjust `working-directory` or use repo-root-relative paths. Place each `--check` right after its board's `ato build`, before/independent of the route step. The existing 0/0 route gate stays.)

- [ ] **Step 2: Commit + push + watch.** Push; watch the `route` job. Expected: **both `--check` steps PASS** (`connectivity matches`) — on the unchanged boards, each build equals its own golden, proving the guard runs end-to-end. The `verified` + `spi_node` route gates still PASS. All 3 jobs green.

```bash
git add .github/workflows/ci.yml
git commit -m "Assert netlist.py --check per board in the route job"
```

### Task 5: PR + merge

- [ ] Open the PR (`--base claude/brainstorm-idea-vegk59 --head feat/netlist-guard`, title "Netlist-equivalence guard: prove the copper matches the design"), confirm all 3 jobs green, `gh pr merge <n> --squash --delete-branch`.

---

# Workstream 2 — extract `Stm32CoreBlock`

**Branch:** `feat/stm32-core`, off trunk **after WS1 merges** (`git fetch && git checkout -b feat/stm32-core origin/claude/brainstorm-idea-vegk59`). **CI-only** (no local `ato build`).

### Task 6: extract the shared core + rewrite both wrappers

**Files:** Modify `spike/atopile/verified_lib.ato`

- [ ] **Step 1: Add `Stm32CoreBlock`** to `verified_lib.ato` (near the MCU blocks). It holds everything `McuBlock` and `McuSpiBlock` currently duplicate, and exposes `power` + `mcu`:

```
# --- Stm32CoreBlock : the shared STM32F103C8T6 core (power + decoupling + reset + boot) -
# Both McuBlock (I2C) and McuSpiBlock (SPI) compose this and add only their bus tail.
# Pure extraction of the previously-duplicated boilerplate — connectivity is unchanged
# (proven by the netlist-equivalence guard in CI).
module Stm32CoreBlock:
    power = new ElectricPower
    mcu = new STMicroelectronics_STM32F103C8T6_package

    mcu.VDD_1 ~ power.hv
    mcu.VDD_2 ~ power.hv
    mcu.VDD_3 ~ power.hv
    mcu.VBAT ~ power.hv
    mcu.VDDA ~ power.hv
    mcu.VSS_1 ~ power.lv
    mcu.VSS_2 ~ power.lv
    mcu.VSS_3 ~ power.lv
    mcu.VSSA ~ power.lv

    dec1 = new Capacitor
    dec2 = new Capacitor
    dec3 = new Capacitor
    bulk = new Capacitor
    deca = new Capacitor
    dec1.capacitance = 100nF +/- 20%
    dec2.capacitance = 100nF +/- 20%
    dec3.capacitance = 100nF +/- 20%
    bulk.capacitance = 4.7uF +/- 20%
    deca.capacitance = 1uF +/- 20%
    dec1.unnamed[0] ~ power.hv
    dec1.unnamed[1] ~ power.lv
    dec2.unnamed[0] ~ power.hv
    dec2.unnamed[1] ~ power.lv
    dec3.unnamed[0] ~ power.hv
    dec3.unnamed[1] ~ power.lv
    bulk.unnamed[0] ~ power.hv
    bulk.unnamed[1] ~ power.lv
    deca.unnamed[0] ~ power.hv
    deca.unnamed[1] ~ power.lv

    nrst_pullup = new Resistor
    nrst_cap = new Capacitor
    nrst_pullup.resistance = 10kohm +/- 5%
    nrst_cap.capacitance = 100nF +/- 20%
    nrst_pullup.unnamed[0] ~ mcu.NRST
    nrst_pullup.unnamed[1] ~ power.hv
    nrst_cap.unnamed[0] ~ mcu.NRST
    nrst_cap.unnamed[1] ~ power.lv

    boot0_pulldown = new Resistor
    boot0_pulldown.resistance = 10kohm +/- 5%
    boot0_pulldown.unnamed[0] ~ mcu.BOOT0
    boot0_pulldown.unnamed[1] ~ power.lv

    assert power.voltage within 3.3V +/- 5%
```

- [ ] **Step 2: Rewrite `McuBlock`** to compose the core + the I2C tail (delete the boilerplate now in the core; keep the public interface `power` + `i2c`):

```
module McuBlock:
    power = new ElectricPower      # 3V3 rail in
    i2c = new I2C                  # I2C1 controller (PB6=SCL, PB7=SDA)
    core = new Stm32CoreBlock
    core.power ~ power

    i2c.scl.reference ~ power
    i2c.sda.reference ~ power
    core.mcu.PB6 ~ i2c.scl.line
    core.mcu.PB7 ~ i2c.sda.line
    scl_pullup = new Resistor
    sda_pullup = new Resistor
    scl_pullup.resistance = 4.7kohm +/- 5%
    sda_pullup.resistance = 4.7kohm +/- 5%
    scl_pullup.unnamed[0] ~ i2c.scl.line
    scl_pullup.unnamed[1] ~ power.hv
    sda_pullup.unnamed[0] ~ i2c.sda.line
    sda_pullup.unnamed[1] ~ power.hv
```

- [ ] **Step 3: Rewrite `McuSpiBlock`** to compose the core + the SPI tail (keep the public interface `power` + `spi` + `cs`):

```
module McuSpiBlock:
    power = new ElectricPower      # 3V3 rail in
    spi = new SPI                  # SPI1 controller (PA5=SCK, PA6=MISO, PA7=MOSI)
    signal cs                      # chip-select (PA4 / SPI1 NSS)
    core = new Stm32CoreBlock
    core.power ~ power

    spi.sclk.reference ~ power
    spi.miso.reference ~ power
    spi.mosi.reference ~ power
    core.mcu.PA5 ~ spi.sclk.line
    core.mcu.PA6 ~ spi.miso.line
    core.mcu.PA7 ~ spi.mosi.line
    core.mcu.PA4 ~ cs
```

(`PowerBlock`/`EepromBlock`/`SpiFlashBlock`/`TempBlock`, the imports, and the two App slices are untouched — both wrappers keep the same public interface, so `verified_slice.ato`/`spi_slice.ato` compose them identically.)

- [ ] **Step 4: Sanity (local, NO build).** Confirm the boilerplate is gone from the wrappers and lives once in the core.

Run: `grep -nE "module Stm32CoreBlock|module McuBlock|module McuSpiBlock|dec1 = new Capacitor|boot0_pulldown" spike/atopile/verified_lib.ato`
Expected: `Stm32CoreBlock`, `McuBlock`, `McuSpiBlock` all present; `dec1 = new Capacitor` and `boot0_pulldown` appear **once** (in the core), not three/two times.

- [ ] **Step 5: Commit + push + watch CI (this is the proof).**

```bash
git add spike/atopile/verified_lib.ato
git commit -m "Extract Stm32CoreBlock; McuBlock + McuSpiBlock compose it (pure refactor)"
git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices.git feat/stm32-core -u
```
Watch the `route` job. **Success = both `netlist.py --check` steps PASS** (`connectivity matches` for verified AND spi_node — the refactor changed nothing electrically) **AND both route gates still PASS (0/0)**.

- [ ] **Step 6 (contingency): if `--check` FAILS** for a board, the refactor changed connectivity — read the printed diff (`+ net ...` / `- part ...`), find the dropped/mis-wired line in the core or a wrapper, fix it, re-push. Do NOT update the golden (the golden is the source of truth — a `--check` failure means the refactor is wrong, not the golden). If `ato build` fails on `core.mcu.<pin>` access, that resolution is the issue — report BLOCKED with the log.

### Task 7: PR + merge

- [ ] Open the PR (`--head feat/stm32-core`, title "Extract shared Stm32CoreBlock (pure refactor, netlist-proven)"), confirm all 3 jobs green (both `--check` pass, both routes 0/0), `gh pr merge <n> --squash --delete-branch`.

---

## Done when

- `netlist.py --selftest` runs in the `spike` job; goldens for both boards are committed; the `route` job `--check`s both boards against golden on every build.
- `verified_lib.ato` has one `Stm32CoreBlock`; `McuBlock`/`McuSpiBlock` no longer duplicate the core boilerplate; their public interfaces are unchanged.
- Both boards' `--check` pass (connectivity == golden, proving the refactor is electrically inert) and both still route 0 unrouted / 0 DRC.
- Both PRs merged to trunk on green.
```
