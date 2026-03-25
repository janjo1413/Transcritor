$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python da virtualenv nao encontrado em .venv\Scripts\python.exe"
}

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name Transcritor `
  --add-data "app\static;app\static" `
  --add-data "app\templates;app\templates" `
  run.py

foreach ($binary in @("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe")) {
    $source = Join-Path $root $binary
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $root "dist\Transcritor\$binary") -Force
    }
}

Write-Host "Build pronta em dist\Transcritor"
