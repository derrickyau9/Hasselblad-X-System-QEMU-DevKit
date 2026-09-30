param([string]$Firmware)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$Packaged = Join-Path $PSScriptRoot 'X2DII-DevKit.exe'
if (Test-Path -LiteralPath $Packaged) {
    if ($Firmware) { & $Packaged $Firmware } else { & $Packaged }
    exit
}
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $BasePython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $BasePython) { throw 'Install Python 3.11+ from python.org, or download the portable DevKit release (no Python installation needed).' }
    & $BasePython.Source -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ required' }
    & $BasePython.Source -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}
$Stamp = Join-Path $PSScriptRoot '.venv\devkit-installed.txt'
if (-not (Test-Path -LiteralPath $Stamp)) {
    & $Python -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; rerun Launch.cmd to retry.' }
    Set-Content -LiteralPath $Stamp -Value '0.1.0'
}
if ($Firmware) { & $Python run_app.py $Firmware } else { & $Python run_app.py }
