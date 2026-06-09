<#
  NL-Devices toolchain setup (Windows / PowerShell) — the pinned, known-good env.
  Mirror of scripts/setup.sh: atopile 0.12.5 on Python 3.13 + spike Python deps.

  atopile >=0.13 requires Python 3.14 (RC, crashes) — see DECISION.md. The 3.13
  pin transitively caps atopile to the 0.12.x line.

  Usage:  ./scripts/setup.ps1     # from the repo root
#>
$ErrorActionPreference = "Stop"

$AtopileVersion = "0.12.5"   # keep in sync with scripts/check_toolchain.py + ato.yaml
$PythonVersion  = "3.13"     # keep in sync with .python-version
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "==> NL-Devices toolchain: atopile==$AtopileVersion, Python $PythonVersion"

# 1. uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> installing uv"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}

# 2. pinned Python + pinned atopile
Write-Host "==> uv python install $PythonVersion"
uv python install $PythonVersion
Write-Host "==> uv tool install atopile==$AtopileVersion --python $PythonVersion"
uv tool install --force "atopile==$AtopileVersion" --python $PythonVersion

# 3. spike Python deps
Write-Host "==> pip install -r spike/requirements.txt"
python -m pip install -r (Join-Path $Root "spike/requirements.txt")

# 4. ngspice (manual on Windows)
if (-not (Get-Command ngspice -ErrorAction SilentlyContinue)) {
    Write-Host "WARN: ngspice not on PATH. Install it (e.g. winget install ngspice) before the electrical gate."
}

# 5. verify
if (-not (Get-Command ato -ErrorAction SilentlyContinue)) {
    throw "'ato' not on PATH after install. Add the uv tools dir (usually ~\.local\bin) and re-run."
}
$atoOut = (ato --version 2>&1) -join " "
if ($atoOut -notmatch [regex]::Escape($AtopileVersion)) {
    throw "ato version is not $AtopileVersion: $atoOut"
}
Write-Host "  OK atopile $AtopileVersion ($atoOut)"
python (Join-Path $Root "scripts/check_toolchain.py")

Write-Host "==> toolchain ready. Build with: cd spike/atopile; ato build -b sensor_node"
