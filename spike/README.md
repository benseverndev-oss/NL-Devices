# Spike — Step 0: Toolchain Baseline (COMPLETE ✅)

Green baseline for the [`SPIKE.md`](../SPIKE.md) bake-off. Establishes that both
substrates and the SPICE-validation leg run end-to-end on a trivial circuit, and
records the environment decisions for the real slice (steps 1–6).

## Result — all three legs green

| Leg | Hello-world | Status | Proven capability |
|---|---|---|---|
| **atopile** | `atopile/` divider → `ato build` | ✅ | Compiles, **constraint solver** runs (post-design/post-solve checks), **JLCPCB part-picker resolves real parts**, emits netlist + BOM + `.kicad_pcb` |
| **SKiDL** | `skidl/hello_skidl.py` | ✅ | Builds circuit, **`ERC()` runs** (correctly flagged the open-ended divider nets), emits a KiCad netlist |
| **SPICE** | `skidl/ngspice_check.py` | ✅ | DC operating point via a **BSD-clean ngspice wrapper** (`V(MID)=2.500V`) |

Evidence — atopile picked a real part for the 10 kΩ 0402:
```
Designator,Footprint,Quantity,Value,Manufacturer,Partnumber,LCSC Part #
"R1, R2",R0402,2,10kΩ ±1% 62.5mW,UNI-ROYAL(Uniroyal Elec),0402WGF1002TCE,C25744
```

## Key findings (feed the bake-off + de-risk later steps)

1. **PySpice is dead for our purposes — confirmed empirically.** PySpice 1.5 (the
   last PyPI release, 2021; GitHub "git" is also 1.5) is **incompatible with ngspice
   42**: the shared-lib path errors `Unsupported Ngspice version 42 / Command 'run'
   failed`, and the subprocess path errors `Expected label Circuit instead of Note`
   (its raw parser chokes on ngspice 42's new header). This is exactly the
   maintenance risk flagged in [`RESEARCH.md`](../RESEARCH.md) §4c.
   → **Decision: drive the `ngspice` binary directly** (`ngspice_check.py`).
   ngspice is **BSD** (safe to embed) vs. PySpice's **GPLv3** — so this also keeps
   the SPICE leg out of our proprietary core, as DESIGN.md intended. SKiDL's own
   `skidl.pyspice` mode is therefore unavailable; not needed.

2. **atopile *does* emit a standalone netlist** (`build/builds/divider/divider/divider.net`)
   alongside `.kicad_pcb`, `divider.bom.csv`, and `*.variables.md` / `*.i2c_tree.md`
   reports. → Resolves the open question in SPIKE.md §8.

3. **atopile part-picking needs network** (hits the JLCPCB/LCSC parts DB; ~5 s for
   2 passives). Works under this environment's network policy. Plan for offline/CI.

4. **Substrate API specifics learned** (for writing the real blocks):
   - atopile `Resistor` exposes `unnamed[0]` / `unnamed[1]` (faebryk); `Electrical`
     and `Resistor` must each be `import`ed. Values are native: `10kohm +/- 5%`.
   - SKiDL needs KiCad symbol libs; we use the **monolithic** format (KiCad tag
     `8.0.0`), not GitLab master's new split `*.kicad_symdir/` layout.

5. **Version note:** atopile installed is **0.12.5** (latest is 0.15.7). Pin/upgrade
   deliberately before step 1 — newer syntax (typed interfaces docs) targets 0.14+.

## Reproduce

**Prereqs (Ubuntu 24.04):**
```bash
apt-get install -y ngspice libngspice0-dev        # ngspice 42 (BSD)
# KiCad symbol libs (monolithic 8.0.0 format) for SKiDL:
git clone --depth 1 --branch 8.0.0 \
  https://gitlab.com/kicad/libraries/kicad-symbols.git spike/kicad-symbols
```

**SKiDL + SPICE leg:**
```bash
cd spike/skidl
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt                   # skidl only (no PySpice)
export KICAD_SYMBOL_DIR=$PWD/../kicad-symbols KICAD8_SYMBOL_DIR=$PWD/../kicad-symbols
python hello_skidl.py        # -> divider.net + ERC
python ngspice_check.py      # -> V(MID)=2.5V  PASS
```

**atopile leg** (Python 3.12+, via `uv`):
```bash
uv python install 3.13
uv tool install atopile --python 3.13             # installs `ato`
cd spike/atopile && ato build                      # -> build/builds/divider/...
```

## Files (committed)
- `atopile/main.ato`, `atopile/ato.yaml` — the atopile divider + build config
- `skidl/hello_skidl.py` — SKiDL divider + ERC + netlist
- `skidl/ngspice_check.py` — **BSD-clean ngspice op-point primitive** (the SPICE
  leg the validator will reuse)
- `skidl/requirements.txt` — pinned deps (skidl only)

Generated dirs (`build/`, `elec/`, `.venv/`, `kicad-symbols/`) are git-ignored.
