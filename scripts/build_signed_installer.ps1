$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Version = if ($args.Count -gt 0) { $args[0] } else { "2.0" }
if ($Version -notmatch '^\d+\.\d+(?:\.\d+)?$') { throw "Invalid release version: $Version" }

$Thumbprint = ($env:VOICE_DICTATION_SIGN_THUMBPRINT -replace '\s', '').ToUpperInvariant()
if (-not $Thumbprint) {
  throw "A trusted Authenticode certificate is required. Set VOICE_DICTATION_SIGN_THUMBPRINT."
}
if ($Thumbprint -notmatch '^[A-F0-9]{40}$') { throw "Invalid Authenticode certificate thumbprint." }
$Certificate = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
  $_.Thumbprint -eq $Thumbprint -and $_.HasPrivateKey
} | Select-Object -First 1
if (-not $Certificate) { throw "The requested Authenticode certificate was not found or has no private key." }

$SignToolCommand = Get-Command signtool.exe -ErrorAction SilentlyContinue
$SignTool = if ($SignToolCommand) { $SignToolCommand.Source } else {
  Get-ChildItem -LiteralPath (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin") `
    -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.DirectoryName -like "*\x64" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1 -ExpandProperty FullName
}
if (-not $SignTool) { throw "Windows signtool.exe was not found." }

$InnoCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$InnoCompiler = if ($InnoCommand) { $InnoCommand.Source } else {
  @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
  ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $InnoCompiler) { throw "Inno Setup 6 is required to build the signed installer." }

$PackageDir = Join-Path $ProjectRoot "dist\VoiceDictation-portable-$Version-signed"
& powershell -NoProfile -ExecutionPolicy RemoteSigned -File (Join-Path $ProjectRoot "scripts\build_portable.ps1") -OutputPath $PackageDir -Version $Version
if ($LASTEXITCODE -ne 0) { throw "Signed portable build failed." }

$TimestampUrl = if ($env:VOICE_DICTATION_TIMESTAMP_URL) { $env:VOICE_DICTATION_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
$TimestampUri = $null
$ValidTimestampUrl = [Uri]::TryCreate($TimestampUrl, [UriKind]::Absolute, [ref]$TimestampUri)
if (-not $ValidTimestampUrl -or $TimestampUri.Scheme -notin @('http', 'https') -or $TimestampUrl -match '[\s"]') {
  throw "Invalid timestamp URL. Use an absolute HTTP or HTTPS URL without whitespace."
}
$TimestampUrl = $TimestampUri.AbsoluteUri
$SignCommand = '"' + $SignTool + '" sign /sha1 ' + $Thumbprint + ' /fd SHA256 /tr "' + $TimestampUrl + '" /td SHA256 $f'
$InstallerDefinition = Join-Path $ProjectRoot "installer\VoiceDictation.iss"
& $InnoCompiler "/DSourceDir=$PackageDir" "/DAppVersion=$Version" "/Srelease=$SignCommand" $InstallerDefinition
if ($LASTEXITCODE -ne 0) { throw "Signed installer build failed." }

$Installer = Join-Path $ProjectRoot "dist\VoiceDictation-Setup-$Version.exe"
$Signature = Get-AuthenticodeSignature -LiteralPath $Installer
if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
  throw "Installer signature verification failed: $($Signature.StatusMessage)"
}
Write-Host "Signed installer: $Installer"
