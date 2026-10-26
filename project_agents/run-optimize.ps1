param(
    [string[]]$Files = @('backend/app/services/comparison_analysis.py', 'backend/tests/test_comparison_analysis.py'),
    [string]$Task = '检查代码，提出保持现有行为的优化建议',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$agentPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $runnerArgs = @('-m', 'project_agents.runner', '--mode', 'optimize', '--task', $Task, '--files') + $Files
    if ($DryRun) { $runnerArgs += '--dry-run' }
    & $agentPython @runnerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Agent run failed; inspect the saved reports.' }
} finally { Pop-Location }
