. (Join-Path $PSScriptRoot 'runtime-path.ps1')
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location (Join-Path $PSScriptRoot 'backend')
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally { Pop-Location }
