"""Offline toolchain-pin consistency gate.

The toolchain pin (atopile 0.12.5 / Python 3.13) is declared in several places —
`ato.yaml`, `.python-version`, and both setup scripts. This lints that they all
agree, so a pin can't silently drift out of sync (e.g. someone bumps `setup.sh` to
0.13 but forgets `ato.yaml`). Pure stdlib, no network, no atopile — safe in the fast
CI job. The *live* install is proven separately by the `toolchain` CI job.

Run:  python3 scripts/check_toolchain.py
"""
from __future__ import annotations

import re
from pathlib import Path

# --- single source of truth for the pin ---------------------------------------
ATOPILE_VERSION = "0.12.5"
PYTHON_VERSION = "3.13"

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _check(label: str, ok: bool, detail: str) -> bool:
    print(f"  [{'ok' if ok else 'FAIL'}] {label:<46} {detail}")
    return ok


def main() -> int:
    print(f"toolchain pin: atopile=={ATOPILE_VERSION}, Python {PYTHON_VERSION}\n" + "-" * 72)
    results = []

    # .python-version pins the project Python to 3.13
    pv = _read(".python-version").strip()
    results.append(_check(".python-version == 3.13", pv == PYTHON_VERSION, repr(pv)))

    # ato.yaml floor must admit 0.12.5 and reference it (the <0.13 ceiling is enforced
    # by the Python 3.13 pin, since 0.13+ needs 3.14).
    ato = _read("spike/atopile/ato.yaml")
    m = re.search(r'requires-atopile:\s*"([^"]+)"', ato)
    spec = m.group(1) if m else ""
    results.append(_check("ato.yaml requires-atopile references 0.12.5",
                          ATOPILE_VERSION in spec, repr(spec)))
    results.append(_check("ato.yaml floor is >= (not a bare/older pin)",
                          spec.startswith(">="), repr(spec)))

    # both setup scripts hard-pin the exact atopile version + the Python version
    for script in ("scripts/setup.sh", "scripts/setup.ps1"):
        s = _read(script)
        results.append(_check(f"{script} pins atopile=={ATOPILE_VERSION}",
                              f"atopile=={ATOPILE_VERSION}" in s or f'atopile=={ATOPILE_VERSION}"' in s
                              or f"atopile==$AtopileVersion" in s or f'atopile==${{ATOPILE_VERSION}}' in s,
                              "via version constant" ))
        results.append(_check(f"{script} declares ATOPILE_VERSION={ATOPILE_VERSION}",
                              re.search(rf'AtopileVersion\s*=\s*"{re.escape(ATOPILE_VERSION)}"', s) is not None
                              or re.search(rf'ATOPILE_VERSION="{re.escape(ATOPILE_VERSION)}"', s) is not None,
                              ""))
        results.append(_check(f"{script} pins Python {PYTHON_VERSION}",
                              re.search(rf'(PYTHON_VERSION="{re.escape(PYTHON_VERSION)}"|'
                                        rf'PythonVersion\s*=\s*"{re.escape(PYTHON_VERSION)}")', s) is not None,
                              ""))

    print("-" * 72)
    ok = all(results)
    print("RESULT:", "PASS - toolchain pins are consistent" if ok
          else "FAIL - toolchain pins disagree across files")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
