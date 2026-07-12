$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"

Push-Location $ProjectRoot
try {
    Write-Host "[1/3] Ensuring Rust toolchain is on PATH..."
    if ((Test-Path $CargoBin) -and -not (($env:PATH -split ";") -contains $CargoBin)) {
        $env:PATH = "$CargoBin;$env:PATH"
    }

    Write-Host "[2/3] Checking Node dependencies..."
    if (-not (Test-Path .\node_modules)) {
        & npm.cmd install
    }

    Write-Host "[3/3] Starting Tauri dev mode with the project virtual environment..."
    Write-Host "Dev mode does not rebuild desktop-runtime."
    & npm.cmd run tauri:dev
}
finally {
    Pop-Location
}
