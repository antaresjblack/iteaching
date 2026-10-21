# Optional: set FFMPEG_BIN to the directory containing ffmpeg.exe and ffprobe.exe.
if ($env:FFMPEG_BIN -and (Test-Path -LiteralPath $env:FFMPEG_BIN)) {
    $env:PATH = "$($env:FFMPEG_BIN);$env:PATH"
}
