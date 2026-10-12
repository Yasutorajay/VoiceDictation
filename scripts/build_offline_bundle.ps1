$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DataModels = Join-Path $ProjectRoot "data\models"
$OutDir = if ($args.Count -gt 0) { (Resolve-Path $args[0]).Path }
"paths:`n  data_dir: data`n" | Set-Content -Encoding UTF8 (Join-Path $OutDir "config.yaml") else { Join-Path $ProjectRoot "dist\VoiceDictation-offline" }
$Wheelhouse = Join-Path $OutDir "wheelhouse"
$DataOut = Join-Path $OutDir "data"
$ModelsOut = Join-Path $DataOut "models"

if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Force -Path $OutDir, $Wheelhouse, $ModelsOut | Out-Null

Write-Host "Downloading pinned runtime wheels..."
python -m pip download --only-binary=:all: --dest $Wheelhouse -r (Join-Path $ProjectRoot "requirements.txt")

if (-not (Test-Path (Join-Path $DataModels "sense-voice-int8\model.int8.onnx"))) {
  throw "Local ASR models are missing. Run scripts\download_models.py first."
}
Write-Host "Copying local models..."
Copy-Item -Recurse -Force (Join-Path $DataModels "*") $ModelsOut

foreach ($item in @("main.py", "config.default.yaml", "requirements.txt", "README.md", "app", "resources", "scripts")) {
  Copy-Item -Recurse -Force (Join-Path $ProjectRoot $item) (Join-Path $OutDir $item)
}

$Launcher = Join-Path $OutDir "启动语音听写-离线.bat"
@"
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python -m pip install --no-index --find-links "%~dp0wheelhouse" -r "%~dp0requirements.txt"
if errorlevel 1 pause & exit /b 1
python main.py
"@ | Set-Content -Encoding UTF8 $Launcher

Write-Host "Offline bundle ready: $OutDir"
