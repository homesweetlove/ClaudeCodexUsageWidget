$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir 'ClaudeCodexUsageWidget.lnk'

if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "Removed startup shortcut: $ShortcutPath"
} else {
    Write-Host "Startup shortcut was not installed."
}
