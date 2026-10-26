$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Please install project_agents dependencies first (see README).' }
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & $python -m project_agents.runner --task '检查评价对比缓存和异常处理，提出最小优化建议并设计回归测试' --files backend/app/services/comparison_analysis.py backend/tests/test_comparison_analysis.py @args
    if ($LASTEXITCODE -ne 0) { throw 'Agent run did not complete; inspect the saved reports.' }
} finally { Pop-Location }