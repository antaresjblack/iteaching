. (Join-Path $PSScriptRoot 'runtime-path.ps1')
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'check_ready.py')
