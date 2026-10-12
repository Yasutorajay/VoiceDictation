param(
  [string]$OutputPath,
  [string]$Version = "2.0"
)

$ErrorActionPreference = "Stop"

function Test-SafeBuildDirectory {
  param([string]$Path, [string]$ApprovedParent, [string]$ExpectedLeaf)
  $Resolved = [IO.Path]::GetFullPath($Path)
  if ([IO.Path]::GetFullPath((Split-Path -Parent $Resolved)) -ne $ApprovedParent) { return $false }
  if ((Split-Path -Leaf $Resolved) -ne $ExpectedLeaf) { return $false }
  if (-not (Test-Path -LiteralPath $Resolved -PathType Container)) { return $false }
  $Attributes = [IO.File]::GetAttributes($Resolved)
  return -not (($Attributes -band [IO.FileAttributes]::ReparsePoint) -eq [IO.FileAttributes]::ReparsePoint)
}

function Assert-PathWithinRoot {
  param([string]$Path, [string]$Root)
  $Resolved = [IO.Path]::GetFullPath($Path)
  $Prefix = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
  if (-not $Resolved.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe package path: $Resolved"
  }
}

function Assert-NoReparsePointTree {
  param([string]$Path, [switch]$SkipRoot)
  $Items = if ($SkipRoot) { @(Get-ChildItem -LiteralPath $Path -Recurse -Force) } else { @(Get-Item -LiteralPath $Path -Force) + @(Get-ChildItem -LiteralPath $Path -Recurse -Force) }
  foreach ($Item in $Items) {
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq [IO.FileAttributes]::ReparsePoint) {
      throw "Reparse point is forbidden in release input: $($Item.FullName)"
    }
  }
}
function Open-ExclusiveBuildLock {
  param([string]$Path)
  return [IO.FileStream]::new(
    $Path,
    [IO.FileMode]::CreateNew,
    [IO.FileAccess]::ReadWrite,
    [IO.FileShare]::None,
    1,
    [IO.FileOptions]::DeleteOnClose
  )
}

function Find-SignTool {
  $Command = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($Command) { return $Command.Source }
  $KitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
  $Candidates = Get-ChildItem -LiteralPath $KitsRoot -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -like "*\x64" } |
    Sort-Object FullName -Descending
  return $Candidates | Select-Object -First 1 -ExpandProperty FullName
}

function Sign-ReleaseExecutable {
  param([string]$Path)
  $Thumbprint = $env:VOICE_DICTATION_SIGN_THUMBPRINT
  if (-not $Thumbprint) {
    Write-Warning "Unsigned development build. Set VOICE_DICTATION_SIGN_THUMBPRINT for a trusted release build."
    return
  }
  $SignTool = Find-SignTool
  if (-not $SignTool) { throw "Windows signtool.exe was not found." }
  $TimestampUrl = if ($env:VOICE_DICTATION_TIMESTAMP_URL) { $env:VOICE_DICTATION_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
  & $SignTool sign /sha1 $Thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path
  if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
  $Signature = Get-AuthenticodeSignature -LiteralPath $Path
  if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Authenticode verification failed: $($Signature.StatusMessage)"
  }
}

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Models = Join-Path $ProjectRoot "data\models"
$ApprovedParent = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "dist"))
$RequestedDist = if ($OutputPath) { $OutputPath } else { Join-Path $ApprovedParent "VoiceDictation-portable" }
$Dist = [IO.Path]::GetFullPath($RequestedDist)
$Zip = "$Dist.zip"
$PublishJournal = Join-Path $ApprovedParent ".$(Split-Path -Leaf $Dist).publish-state"

if ((Split-Path -Leaf $Dist) -notmatch '^VoiceDictation-portable(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?$' -or
    [IO.Path]::GetFullPath((Split-Path -Parent $Dist)) -ne $ApprovedParent) {
  throw "Unsafe portable output path: $Dist"
}
if (-not (Test-Path -LiteralPath (Join-Path $Models "sense-voice-int8\model.int8.onnx") -PathType Leaf)) {
  throw "ASR model missing. Run scripts\download_models.py first."
}

New-Item -ItemType Directory -Force -Path $ApprovedParent | Out-Null
Assert-NoReparsePointTree $ProjectRoot -SkipRoot
foreach ($InputPath in @($Models, (Join-Path $ProjectRoot "resources"), $ApprovedParent)) {
  Assert-NoReparsePointTree $InputPath
}
$PublishLock = $null
$BuildOwner = $null
$BuildRoot = $null
$BuildLeaf = $null
$StagedDist = $null
$PublishStarted = $false
$PublishedZip = $false

try {
  if (Test-Path -LiteralPath $Dist) { throw "Portable output already exists: $Dist" }
  if (Test-Path -LiteralPath $Zip) { throw "Zip output already exists: $Zip" }

  $PublishLockPath = "$Dist.publish.lock"
  $PublishLock = Open-ExclusiveBuildLock $PublishLockPath
  if (Test-Path -LiteralPath $PublishJournal) {
    throw "An interrupted publish needs recovery before rebuilding: $PublishJournal"
  }
  if (Test-Path -LiteralPath $Dist) { throw "Portable output was created by another process: $Dist" }
  if (Test-Path -LiteralPath $Zip) { throw "Zip output was created by another process: $Zip" }

  $BuildLeaf = ".VoiceDictation-build-$([Guid]::NewGuid().ToString("N"))"
  $BuildRoot = Join-Path $ApprovedParent $BuildLeaf
  New-Item -ItemType Directory -Path $BuildRoot | Out-Null
  if (-not (Test-SafeBuildDirectory $BuildRoot $ApprovedParent $BuildLeaf)) {
    throw "Unsafe temporary build directory: $BuildRoot"
  }
  $BuildOwner = Open-ExclusiveBuildLock (Join-Path $BuildRoot ".owner.lock")
  if (-not (Test-SafeBuildDirectory $BuildRoot $ApprovedParent $BuildLeaf)) {
    throw "Temporary build directory changed unexpectedly: $BuildRoot"
  }

  $StagedDist = Join-Path $BuildRoot (Split-Path -Leaf $Dist)
  $PyInstallerDist = Join-Path $BuildRoot "pyinstaller-dist"
  $PyInstallerWork = Join-Path $BuildRoot "pyinstaller-work"
  $PyInstallerSpec = Join-Path $BuildRoot "pyinstaller-spec"

  Push-Location $ProjectRoot
  try {
    & python tools\collect_third_party_licenses.py
    if ($LASTEXITCODE -ne 0) { throw "Third-party license collection failed." }
    $GeneratedVersionInfo = Join-Path $BuildRoot "version_info.txt"
    & python tools\release_version_info.py resources\version_info.txt $GeneratedVersionInfo $Version
    if ($LASTEXITCODE -ne 0) { throw "Version resource generation failed." }
    $Excludes = @(
      "torch", "torchvision", "torchaudio", "tensorflow", "transformers",
      "pandas", "matplotlib", "sklearn", "cv2", "openpyxl", "lxml",
      "nltk", "kivy", "kivymd", "playwright", "patchright", "pytest",
      "IPython", "jupyter", "sympy", "fastapi", "uvicorn", "pydantic",
      "requests", "urllib3", "cryptography", "onnxruntime", "soundfile"
    )
    $ExcludeArgs = @()
    foreach ($Module in $Excludes) { $ExcludeArgs += @("--exclude-module", $Module) }
    & python -m PyInstaller --noconfirm --clean --noupx --onedir --windowed --name VoiceDictation `
      --distpath $PyInstallerDist --workpath $PyInstallerWork --specpath $PyInstallerSpec `
      --version-file $GeneratedVersionInfo `
      --icon (Join-Path $ProjectRoot "resources\VoiceDictation.ico") @ExcludeArgs main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
  } finally {
    Pop-Location
  }

  New-Item -ItemType Directory -Path $StagedDist | Out-Null
  $BuiltApplication = Join-Path $PyInstallerDist "VoiceDictation"
  Sign-ReleaseExecutable (Join-Path $BuiltApplication "VoiceDictation.exe")
  Copy-Item -Path (Join-Path $BuiltApplication "*") -Destination $StagedDist -Recurse -Force

  $PortAudioDestination = Join-Path $StagedDist "_internal\_sounddevice_data\portaudio-binaries"
  New-Item -ItemType Directory -Force -Path $PortAudioDestination | Out-Null
  $PortAudioDestinationFile = Join-Path $PortAudioDestination "libportaudio64bit.dll"
  & python -c "import shutil, sys; from pathlib import Path; import _sounddevice_data; source=Path(next(iter(_sounddevice_data.__path__)))/'portaudio-binaries'/'libportaudio64bit.dll'; assert source.is_file(), source; shutil.copy2(source, Path(sys.argv[1]))" $PortAudioDestinationFile
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PortAudioDestinationFile -PathType Leaf)) {
    throw "Unable to copy the PortAudio runtime."
  }

  Copy-Item -LiteralPath $Models -Destination (Join-Path $StagedDist "models") -Recurse -Force
  Copy-Item -LiteralPath (Join-Path $ProjectRoot "resources") -Destination (Join-Path $StagedDist "resources") -Recurse -Force
  foreach ($Name in @("README.md", "LICENSE_OR_TERMS_ZH.txt", "USER_GUIDE_ZH.md")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $Name) -Destination (Join-Path $StagedDist $Name) -Force
  }
  $ThirdParty = Join-Path $StagedDist "ThirdPartyLicenses"
  New-Item -ItemType Directory -Path $ThirdParty | Out-Null
  Copy-Item -LiteralPath (Join-Path $ProjectRoot "resources\licenses") -Destination (Join-Path $ThirdParty "licenses") -Recurse -Force
  Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.txt") -Destination (Join-Path $ThirdParty "THIRD_PARTY_NOTICES.txt") -Force

  Copy-Item -LiteralPath (Join-Path $ProjectRoot "config.default.yaml") -Destination (Join-Path $StagedDist "config.yaml") -Force
  $PortableConfigPath = Join-Path $StagedDist "config.yaml"
  $PortableConfig = Get-Content -LiteralPath $PortableConfigPath -Raw -Encoding UTF8
  $PortableConfig = [regex]::Replace($PortableConfig, '(?ms)^paths:\s+data_dir:\s*.*?\r?\n', "paths:`r`n  data_dir: data`r`n")
  $PortableConfig | Set-Content -LiteralPath $PortableConfigPath -Encoding UTF8
  New-Item -ItemType Directory -Path (Join-Path $StagedDist "data") | Out-Null
  Move-Item -LiteralPath (Join-Path $StagedDist "models") -Destination (Join-Path $StagedDist "data\models")

  $CustomerDevFiles = @(
    "resources\README.md",
    "data\models\sense-voice-int8\README.md",
    "data\models\punct-ct-transformer-int8\README.md",
    "data\models\punct-ct-transformer-int8\add-model-metadata.py",
    "data\models\punct-ct-transformer-int8\show-model-input-output.py",
    "data\models\punct-ct-transformer-int8\test.py"
  )
  foreach ($Relative in $CustomerDevFiles) {
    $Candidate = Join-Path $StagedDist $Relative
    Assert-PathWithinRoot $Candidate $StagedDist
    if (Test-Path -LiteralPath $Candidate) { Remove-Item -LiteralPath $Candidate -Force }
  }
  $DeliveryLogs = Join-Path $StagedDist "data\logs"
  Assert-PathWithinRoot $DeliveryLogs $StagedDist
  if (Test-Path -LiteralPath $DeliveryLogs) { Remove-Item -LiteralPath $DeliveryLogs -Recurse -Force }

  @"
@echo off
cd /d "%~dp0"
VoiceDictation.exe
if errorlevel 1 pause
"@ | Set-Content -Encoding ASCII (Join-Path $StagedDist "start_voice_dictation.bat")

  @"
@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_package.ps1"
pause
"@ | Set-Content -Encoding ASCII (Join-Path $StagedDist "verify_package.bat")

  @'
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Manifest = Join-Path $Root "SHA256SUMS.txt"
$Errors = [System.Collections.Generic.List[string]]::new()
foreach ($Line in Get-Content -LiteralPath $Manifest -Encoding ASCII) {
  if ($Line -notmatch '^([0-9A-F]{64}) \*(.+)$') {
    $Errors.Add("Invalid manifest line")
    continue
  }
  $Expected = $Matches[1]
  $Relative = $Matches[2].Replace('/', '\')
  $Path = Join-Path $Root $Relative
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    $Errors.Add("Missing: $Relative")
    continue
  }
  $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
  if ($Actual -ne $Expected) { $Errors.Add("Hash mismatch: $Relative") }
}
if ($Errors.Count -gt 0) {
  $Errors | ForEach-Object { Write-Host $_ -ForegroundColor Red }
  exit 1
}
Write-Host "Package verification passed." -ForegroundColor Green
exit 0
'@ | Set-Content -Encoding UTF8 (Join-Path $StagedDist "verify_package.ps1")

  @"
VoiceDictation portable package
Extract the entire folder, then run start_voice_dictation.bat or VoiceDictation.exe.
Hold Right Alt and click Middle Mouse to dictate.
Double-press F10 to open the fallback text box for live preview and copying the latest result.
Pin it on top of other windows with the pin button in its bottom bar.
Keep VoiceDictation.exe together with its _internal, data, and resources folders.
For help, read USER_GUIDE_ZH.md. Third-party legal notices are in ThirdPartyLicenses.
"@ | Set-Content -Encoding UTF8 (Join-Path $StagedDist "README_PORTABLE.txt")

  & python -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from scripts.release_audit import audit_portable_tree; errors=audit_portable_tree(Path(sys.argv[2])); print(chr(10).join(errors)); sys.exit(bool(errors))" $ProjectRoot $StagedDist
  if ($LASTEXITCODE -ne 0) { throw "Release content audit failed." }

  & python -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from scripts.portable_integrity import validate_manifest, validate_portable_tree, write_manifest; root=Path(sys.argv[2]); manifest=root/'SHA256SUMS.txt'; missing=validate_portable_tree(root); assert not missing, missing; write_manifest(root, manifest); errors=validate_manifest(root, manifest); assert not errors, errors" $ProjectRoot $StagedDist
  if ($LASTEXITCODE -ne 0) { throw "Portable integrity check failed." }
  if (Test-Path -LiteralPath $DeliveryLogs) { throw "Delivery package must not contain logs or recordings." }

  $StagedZip = Join-Path $BuildRoot "portable.zip"
  Compress-Archive -LiteralPath $StagedDist -DestinationPath $StagedZip -CompressionLevel Fastest
  & python -c "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from scripts.release_audit import audit_zip_against_tree; errors=audit_zip_against_tree(Path(sys.argv[2]), Path(sys.argv[3])); print(chr(10).join(errors)); sys.exit(bool(errors))" $ProjectRoot $StagedZip $StagedDist
  if ($LASTEXITCODE -ne 0) { throw "Final ZIP audit failed." }
  if (Test-Path -LiteralPath $Dist) { throw "Portable output was created during the build: $Dist" }
  if (Test-Path -LiteralPath $Zip) { throw "Zip output was created during the build: $Zip" }

  @{
    directory = $Dist
    zip = $Zip
    stagedDirectory = $StagedDist
    stagedZip = $StagedZip
  } | ConvertTo-Json | Set-Content -LiteralPath $PublishJournal -Encoding UTF8
  $PublishStarted = $true
  try {
    Move-Item -LiteralPath $StagedDist -Destination $Dist
    Move-Item -LiteralPath $StagedZip -Destination $Zip
    $PublishedZip = $true
  } catch {
    $RollbackErrors = [System.Collections.Generic.List[string]]::new()
    if ($PublishedZip -and (Test-Path -LiteralPath $Zip)) {
      try { Remove-Item -LiteralPath $Zip -Force } catch { $RollbackErrors.Add("zip cleanup: $($_.Exception.Message)") }
    }
    if ((Test-Path -LiteralPath $Dist) -and -not (Test-Path -LiteralPath $StagedDist)) {
      try { Move-Item -LiteralPath $Dist -Destination $StagedDist } catch { $RollbackErrors.Add("directory rollback: $($_.Exception.Message)") }
    }
    if ($RollbackErrors.Count -gt 0) {
      throw "Publish failed and requires recovery. Transaction record: $PublishJournal. $($RollbackErrors -join '; ')"
    }
    Remove-Item -LiteralPath $PublishJournal -Force
    throw
  }
  Remove-Item -LiteralPath $PublishJournal -Force
  $PublishStarted = $false

  Write-Host "Portable package: $Dist"
  Write-Host "Zip package: $Zip"
} finally {
  if ($BuildOwner) { $BuildOwner.Dispose() }
  if ($PublishLock) { $PublishLock.Dispose() }
  if ($BuildRoot -and (Test-Path -LiteralPath $BuildRoot)) {
    if (-not (Test-SafeBuildDirectory $BuildRoot $ApprovedParent $BuildLeaf)) {
      throw "Refusing to clean unsafe temporary build directory: $BuildRoot"
    }
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
  }
}
