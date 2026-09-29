# Compatibility wrapper; no personal paths and no existing hook replacement.
param([string]$Repo = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $Repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = 'python' }
& $taskPython (Join-Path $PSScriptRoot 'install_pre_commit.py') --repo $Repo
exit $LASTEXITCODE
