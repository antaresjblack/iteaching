# Prefer a repository-local environment; reuse the existing parent environment on this machine.
$script:ProjectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $script:ProjectPython)) {
    $script:ProjectPython = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $script:ProjectPython)) {
    throw 'Python environment missing. Follow README to create .venv.'
}
$ffmpegDirectory = $env:FFMPEG_BIN
if (-not $ffmpegDirectory) { $ffmpegDirectory = 'D:\tools\ffmpeg-9.0.2-essentials_build\bin' }
if (Test-Path -LiteralPath $ffmpegDirectory) {
    $env:PATH = "$ffmpegDirectory;$env:PATH"
}
