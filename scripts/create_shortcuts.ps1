param(
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$exe = Join-Path $InstallDir "VoiceDictation.exe"
$icon = Join-Path $InstallDir "resources\VoiceDictation.ico"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "VoiceDictation.exe not found: $exe"
}

$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopLink = $shell.CreateShortcut((Join-Path $desktop "VoiceDictation.lnk"))
$desktopLink.TargetPath = $exe
$desktopLink.WorkingDirectory = $InstallDir
$desktopLink.IconLocation = "$icon,0"
$desktopLink.Description = "Voice dictation"
$desktopLink.Save()

Write-Output "Desktop shortcut created: $desktop\VoiceDictation.lnk"
