. (Join-Path $PSScriptRoot 'runtime-path.ps1')
& ($script:ProjectPython) (Join-Path $PSScriptRoot 'check_ready.py')
