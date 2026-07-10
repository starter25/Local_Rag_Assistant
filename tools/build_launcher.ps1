$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Launcher = Join-Path $ProjectRoot "tools\local_rag_launcher.py"

if (-not (Test-Path $Python)) {
    throw "venv Python을 찾지 못했습니다: $Python"
}

& $Python -m PyInstaller `
    --noconfirm `
    --onefile `
    --noconsole `
    --name "LocalRAGAssistant" `
    --distpath (Join-Path $ProjectRoot "dist") `
    --workpath (Join-Path $ProjectRoot "build") `
    --specpath (Join-Path $ProjectRoot "build") `
    $Launcher

Write-Host ""
Write-Host "완료: $(Join-Path $ProjectRoot 'dist\LocalRAGAssistant.exe')"
