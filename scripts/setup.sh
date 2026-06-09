#!/usr/bin/env bash
# NL-Devices toolchain setup — the pinned, known-good environment (DECISION.md step 1).
#
#   atopile 0.12.5  ·  Python 3.13  ·  ngspice (BSD)  ·  spike Python deps
#
# Why pinned: atopile >=0.13 requires Python 3.14, which is only at RC and whose CLI
# crashed on 3.14.0rc2 (DECISION.md §"Version churn"). 0.12.5 on 3.13 is the
# substrate the whole spike was built and verified on. The Python pin also
# transitively caps atopile: a 3.13 toolchain can't install the 3.14-only 0.13 line.
#
# Usage:  ./scripts/setup.sh        # from the repo root (or anywhere)
set -euo pipefail

ATOPILE_VERSION="0.12.5"   # keep in sync with scripts/check_toolchain.py + ato.yaml
PYTHON_VERSION="3.13"      # keep in sync with .python-version
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"   # where uv installs itself + tool shims

echo "==> NL-Devices toolchain: atopile==${ATOPILE_VERSION}, Python ${PYTHON_VERSION}"

# 1. uv — manages the pinned Python and the atopile tool install
if ! command -v uv >/dev/null 2>&1; then
  echo "==> installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. pinned Python + pinned atopile (idempotent; --force re-pins an existing install)
echo "==> uv python install ${PYTHON_VERSION}"
uv python install "${PYTHON_VERSION}"
echo "==> uv tool install atopile==${ATOPILE_VERSION} --python ${PYTHON_VERSION}"
uv tool install --force "atopile==${ATOPILE_VERSION}" --python "${PYTHON_VERSION}"

# 3. spike Python deps (validator / contract / orchestrator / planner)
echo "==> pip install -r spike/requirements.txt"
python3 -m pip install -r "${ROOT}/spike/requirements.txt"

# 4. ngspice — the BSD electrical-gate backend (report; don't assume a package manager)
if ! command -v ngspice >/dev/null 2>&1; then
  echo "WARN: ngspice not on PATH. Install it before running the electrical gate:"
  echo "        Ubuntu/Debian: sudo apt-get install -y ngspice"
  echo "        macOS:         brew install ngspice"
fi

# 5. verify the pins actually resolved
echo "==> verifying"
if ! command -v ato >/dev/null 2>&1; then
  echo "ERROR: 'ato' not on PATH after install (expected ~/.local/bin). Add it and re-run." >&2
  exit 1
fi
ATO_OUT="$(ato --version 2>&1 || true)"
case "${ATO_OUT}" in
  *"${ATOPILE_VERSION}"*) echo "  ✓ atopile ${ATOPILE_VERSION} (${ATO_OUT})" ;;
  *) echo "ERROR: ato version is not ${ATOPILE_VERSION}: ${ATO_OUT}" >&2; exit 1 ;;
esac
python3 "${ROOT}/scripts/check_toolchain.py"

echo "==> toolchain ready. Build with: (cd spike/atopile && ato build -b sensor_node)"
