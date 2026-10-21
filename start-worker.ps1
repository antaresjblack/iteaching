. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try { & $python -m iteaching_ai.worker } finally { Pop-Location }
