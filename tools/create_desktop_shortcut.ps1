$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ExePath = Join-Path $ProjectRoot "dist\LocalRAGAssistant.exe"

if (-not (Test-Path $ExePath)) {
    throw "런처 EXE를 찾지 못했습니다. 먼저 .\tools\build_launcher.ps1 을 실행해 주세요: $ExePath"
}

$DesktopCandidates = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:USERPROFILE "OneDrive\Desktop")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

$Shell = New-Object -ComObject WScript.Shell

foreach ($Desktop in $DesktopCandidates) {
    $ShortcutPath = Join-Path $Desktop "Local RAG Assistant.lnk"
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $ExePath
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = "Local RAG Assistant 실행"
    $Shortcut.IconLocation = "$ExePath,0"
    $Shortcut.Save()

    Write-Host "완료: $ShortcutPath"
}
