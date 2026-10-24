. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$ErrorActionPreference = 'Stop'
$python = $script:ProjectPython
Push-Location $PSScriptRoot
try { & $python -m iteaching_ai.worker } finally { Pop-Location }
