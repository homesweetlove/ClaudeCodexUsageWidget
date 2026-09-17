$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir 'ClaudeCodexUsageWidget.lnk'
$RunBat = Join-Path $ProjectDir 'run.bat'

if (-not (Test-Path $RunBat)) {
    throw "run.bat was not found at $RunBat"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $RunBat
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Claude + Codex local usage widget'
$Shortcut.Save()

Write-Host "Installed startup shortcut: $ShortcutPath"
