$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot 'frontend')
try { npm.cmd run dev -- --host localhost } finally { Pop-Location }
