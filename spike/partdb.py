"""Ground-truth part-data layer — back each verified block's `bound_part` with
real, sourced component data instead of trusting hand-typed YAML.

GAPS.md §4d: today a typo in a block's YAML (wrong LCSC code, MPN, footprint, or
voltage) is *undetectable* — there is no ground truth to check it against. This
module closes that: it ingests authoritative data per LCSC part number and pins it
into `parts_snapshot.json`, which `verify_parts.py` checks every block against
offline (deterministic, network-free CI).

Two layers, deliberately split by trust model:

  * **ingest** (this file, networked, run occasionally) — pulls from EasyEDA's
    component API (identity + exact KiCad package descriptor + stock) and the LCSC
    product page's embedded `__NEXT_DATA__` parametric table (electrical attrs).
    Brittle by nature; it only ever *writes the snapshot*.
  * **verify** (`verify_parts.py`, offline, run in CI) — reads the committed
    snapshot only. The pinned snapshot is the reproducible artifact; the network is
    never on the CI path.

What ground truth actually covers (be honest — see verify_parts.py report):
  VERIFIABLE today: LCSC code exists, MPN, manufacturer (alias-matched), footprint
  family, fixed output voltage (LDOs), operating-voltage range, output-current
  capacity, bus interface.
  NOT yet ground-truthed: I2C address_base, tolerances, pin-level data — these stay
  trusted-but-unverified and are flagged as such, not silently blessed.

Run:
  pip install requests                       # ingest-only dep (not needed for CI/verify)
  python3 partdb.py ingest --from-blocks     # refresh snapshot for every block's part
  python3 partdb.py ingest C6186 C8734       # refresh specific LCSC codes
  python3 partdb.py show C6186               # print one snapshot record
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
SNAPSHOT = HERE / "parts_snapshot.json"
SCHEMA_VERSION = "1.0"

# Browser-ish headers — EasyEDA sits behind CloudFront and 403s a bare UA; the
# Referer/Origin pair is what makes the component API answer.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_EASYEDA_HEADERS = {"User-Agent": _UA, "Accept": "application/json, text/plain, */*",
                    "Referer": "https://easyeda.com/", "Origin": "https://easyeda.com"}
_LCSC_HEADERS = {"User-Agent": _UA}


# ---- canonical record --------------------------------------------------------
@dataclass
class PartRecord:
    """Ground truth for one LCSC part. `attributes` holds parsed canonical values;
    `raw_attributes` keeps exactly what the source returned, for audit/provenance."""
    lcsc: str
    mpn: str | None = None
    manufacturer: str | None = None
    package: str | None = None              # full KiCad-style descriptor from EasyEDA
    jlcpcb_class: str | None = None         # "Basic Part" | "Extended Part"
    stock: int | None = None
    lcsc_url: str | None = None
    easyeda_uuid: str | None = None
    attributes: dict = field(default_factory=dict)      # canonical, parsed
    raw_attributes: list = field(default_factory=list)  # [[name, value], ...] verbatim
    fetched_at: str | None = None
    sources: list = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "PartRecord":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


# ---- snapshot IO -------------------------------------------------------------
def load_snapshot(path: Path = SNAPSHOT) -> dict[str, PartRecord]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {code: PartRecord.from_json(rec) for code, rec in doc.get("parts", {}).items()}


def save_snapshot(parts: dict[str, PartRecord], path: Path = SNAPSHOT,
                  *, generated_at: str | None = None) -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "source": "easyeda+lcsc",
        "generated_by": "partdb.py ingest",
        "generated_at": generated_at,
        "note": ("Ground-truth part data. Regenerate with `python3 partdb.py ingest "
                 "--from-blocks`. verify_parts.py checks blocks against this offline."),
        "parts": {code: parts[code].to_json() for code in sorted(parts)},
    }
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---- normalization (shared by the verifier) ----------------------------------
# Manufacturer naming differs wildly across LCSC/EasyEDA/our YAML (zh suffixes,
# abbreviations). Treat manufacturer as a soft/aliased match, never a hard fail.
_MFR_ALIASES = {
    "st": "stmicroelectronics", "stmicroelectronics": "stmicroelectronics",
    "ti": "texasinstruments", "texasinstruments": "texasinstruments",
    "microchip": "microchiptech", "microchiptech": "microchiptech",
    "advancedmonolithicsystems": "advancedmonolithicsystems", "ams": "advancedmonolithicsystems",
}


def _mfr_key(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"[(（].*?[)）]", "", s)          # drop "(意法半导体)" style suffixes
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return _MFR_ALIASES.get(s, s)


def manufacturer_matches(block_mfr: str | None, gt_mfr: str | None) -> bool:
    a, b = _mfr_key(block_mfr), _mfr_key(gt_mfr)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def norm_mpn(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "").upper())


def _pkg_family(s: str | None) -> str:
    """Leading package family token, e.g. 'SOIC-8_L4.9-W3.9...' -> 'SOIC-8'."""
    if not s:
        return ""
    return re.split(r"[_\s]", s.strip())[0].upper()


def footprint_matches(block_fp: str | None, gt_package: str | None) -> bool:
    bf, gp = (block_fp or "").upper().replace(" ", ""), (gt_package or "").upper().replace(" ", "")
    if not bf or not gp:
        return False
    # block footprints are the family token ("SOIC-8", "LQFP-48", "SOT-223-3");
    # ground-truth package prefixes it with full dimensions.
    return gp.startswith(bf) or _pkg_family(gt_package) == _pkg_family(block_fp)


# ---- attribute parsing -------------------------------------------------------
def parse_voltage_v(raw: str) -> dict | None:
    """'2V~3.6V' -> {min,max}; '15V' -> {min:None,max} (single = rating ceiling);
    '3.3V' callers that want a point value use .get('max') when min is None."""
    if not raw:
        return None
    vals = [float(x) for x in re.findall(r"(-?\d+(?:\.\d+)?)\s*V\b", raw)]
    if not vals:
        return None
    if "~" in raw and len(vals) >= 2:
        return {"min": min(vals), "max": max(vals), "raw": raw}
    return {"min": None, "max": vals[0], "value": vals[0], "raw": raw}


def parse_current_ma(raw: str) -> dict | None:
    if not raw:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(uA|µA|mA|A)\b", raw)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2)
    ma = {"uA": v / 1000.0, "µA": v / 1000.0, "mA": v, "A": v * 1000.0}[unit]
    return {"value_ma": ma, "raw": raw}


# Chinese LCSC attribute key -> (canonical name, parser). Values are already English.
_ATTR_MAP = {
    "工作电压": ("operating_voltage_v", parse_voltage_v),     # operating / input voltage (range or ceiling)
    "输出电压": ("output_voltage_v", parse_voltage_v),         # fixed regulator output
    "输出电流": ("output_current_ma", parse_current_ma),       # regulator output capacity
    "接口类型": ("interface", None),                            # "I2C" / "SPI" / ...
    "静态电流(Iq)": ("quiescent_current_ma", parse_current_ma),
    "待机电流": ("standby_current_ma", parse_current_ma),
}


def normalize_attributes(raw_pairs: list[tuple[str, str]]) -> dict:
    """raw [[zh_name, value], ...] -> canonical parsed dict. Unknown keys are kept
    only in raw_attributes (provenance); known keys become checkable fields."""
    out: dict = {}
    for name, value in raw_pairs:
        if name not in _ATTR_MAP:
            continue
        canon, parser = _ATTR_MAP[name]
        if parser is None:
            out[canon] = [t.strip() for t in re.split(r"[;,/]", str(value)) if t.strip()]
        else:
            parsed = parser(str(value))
            if parsed is not None:
                out[canon] = parsed
    return out


# ---- network ingest (requests imported lazily; not a CI dependency) ----------
def _fetch_easyeda(code: str) -> dict:
    import requests
    r = requests.get(f"https://easyeda.com/api/products/{code}/components",
                     headers=_EASYEDA_HEADERS, params={"version": "6.5.46"}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if not d.get("success"):
        raise RuntimeError(f"EasyEDA returned success=false for {code}")
    res = d.get("result") or {}
    cpara = ((res.get("dataStr") or {}).get("head") or {}).get("c_para") or {}
    sz = res.get("szlcsc") or {}
    return {
        "mpn": cpara.get("Manufacturer Part") or res.get("title"),
        "manufacturer": cpara.get("Manufacturer"),
        "package": cpara.get("package"),
        "jlcpcb_class": cpara.get("JLCPCB Part Class"),
        "stock": sz.get("stock"),
        "easyeda_uuid": res.get("uuid"),
    }


def _fetch_lcsc(code: str) -> dict:
    """Pull the parametric attribute table + clean English brand from the product
    page's embedded __NEXT_DATA__ JSON."""
    import requests
    html = requests.get(f"https://www.lcsc.com/product-detail/{code}.html",
                        headers=_LCSC_HEADERS, timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {"raw_attributes": [], "brand": None}
    data = json.loads(m.group(1))
    pairs: list[list[str]] = []
    brand = {"v": None}

    def walk(o):
        if isinstance(o, dict):
            if "paramName" in o and ("paramValueEn" in o or "paramValue" in o):
                pairs.append([o.get("paramName"), o.get("paramValueEn") or o.get("paramValue")])
            if not brand["v"] and o.get("brandNameEn"):
                brand["v"] = o["brandNameEn"]
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return {"raw_attributes": pairs, "brand": brand["v"]}


def build_record(code: str, *, fetched_at: str | None = None) -> PartRecord:
    eda = _fetch_easyeda(code)
    lcsc = _fetch_lcsc(code)
    raw = lcsc["raw_attributes"]
    return PartRecord(
        lcsc=code,
        mpn=eda["mpn"],
        manufacturer=lcsc["brand"] or eda["manufacturer"],   # prefer clean English brand
        package=eda["package"],
        jlcpcb_class=eda["jlcpcb_class"],
        stock=eda["stock"],
        lcsc_url=f"https://www.lcsc.com/product-detail/{code}.html",
        easyeda_uuid=eda["easyeda_uuid"],
        attributes=normalize_attributes(raw),
        raw_attributes=raw,
        fetched_at=fetched_at,
        sources=["easyeda:components", "lcsc:__NEXT_DATA__"],
    )


def _codes_from_blocks() -> list[str]:
    import block_contract  # local sibling module
    out = []
    for b in block_contract.load_blocks().values():
        if b.bound_part and b.bound_part.get("lcsc"):
            out.append(b.bound_part["lcsc"])
    return sorted(set(out))


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _cmd_ingest(args: list[str]) -> int:
    from_blocks = "--from-blocks" in args
    codes = [a for a in args if a.upper().startswith("C") and a[1:].isdigit()]
    if from_blocks:
        codes = sorted(set(codes) | set(_codes_from_blocks()))
    if not codes:
        print("nothing to ingest. give LCSC codes or --from-blocks", file=sys.stderr)
        return 2
    parts = load_snapshot()
    today = _today()
    for code in codes:
        try:
            parts[code] = build_record(code, fetched_at=today)
            r = parts[code]
            print(f"  ✓ {code:<10} {r.mpn:<22} {r.package:<34} "
                  f"attrs={list(r.attributes)}")
        except Exception as e:                       # noqa: BLE001 — surface, keep going
            print(f"  ✗ {code:<10} FAILED: {e}", file=sys.stderr)
    save_snapshot(parts, generated_at=today)
    print(f"\nwrote {SNAPSHOT.relative_to(HERE.parent)} ({len(parts)} parts)")
    return 0


def _cmd_show(args: list[str]) -> int:
    parts = load_snapshot()
    for code in args:
        rec = parts.get(code)
        print(json.dumps(rec.to_json(), indent=2, ensure_ascii=False) if rec
              else f"{code}: not in snapshot")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # zh attr values on Windows consoles
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ingest":
        raise SystemExit(_cmd_ingest(sys.argv[2:]))
    if cmd == "show":
        raise SystemExit(_cmd_show(sys.argv[2:]))
    print(__doc__)
    raise SystemExit(0)
