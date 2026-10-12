$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Required = @(
    "VoiceDictation.exe",
    "config.yaml",
    "_internal\python312.dll",
    "_internal\VCRUNTIME140.dll",
    "_internal\VCRUNTIME140_1.dll",
    "_internal\ucrtbase.dll",
    "_internal\_sounddevice_data\portaudio-binaries\libportaudio64bit.dll",
    "data\models\sense-voice-int8\model.int8.onnx",
    "data\models\sense-voice-int8\tokens.txt",
    "data\models\punct-ct-transformer-int8\model.int8.onnx",
    "data\models\punct-ct-transformer-int8\tokens.json",
    "data\models\silero_vad.onnx",
    "resources\ai_terms.yaml",
    "resources\VoiceDictation.ico"
)

$Missing = @($Required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Root $_) -PathType Leaf) })
if ($Missing.Count -gt 0) {
    Write-Host "Offline package is incomplete." -ForegroundColor Red
    $Missing | ForEach-Object { Write-Host "Missing: $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Offline package is complete." -ForegroundColor Green
Write-Host "Python runtime, VC runtime, audio runtime, models and resources are included."
exit 0
