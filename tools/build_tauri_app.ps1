$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"

Push-Location $ProjectRoot
try {
    Write-Host "[1/4] Ensuring Rust toolchain is on PATH..."
    if ((Test-Path $CargoBin) -and -not (($env:PATH -split ";") -contains $CargoBin)) {
        $env:PATH = "$CargoBin;$env:PATH"
    }

    Write-Host "[2/4] Preparing the desktop runtime bundle..."
    & powershell -ExecutionPolicy Bypass -File .\tools\prepare_tauri_runtime.ps1

    Write-Host "[3/4] Checking Node dependencies..."
    if (-not (Test-Path .\node_modules)) {
        & npm.cmd install
    }

    Write-Host "[4/4] Building the MSI bundle..."
    & npm.cmd run tauri:build:msi
}
finally {
    Pop-Location
}
