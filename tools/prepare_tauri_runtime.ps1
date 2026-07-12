$ErrorActionPreference = "Stop"

function Remove-PathIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathToRemove
    )

    if (Test-Path $PathToRemove) {
        Remove-Item -LiteralPath $PathToRemove -Recurse -Force
    }
}

function Remove-TreeByName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )

    if (-not (Test-Path $Root)) {
        return
    }

    Get-ChildItem -Path $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $Names -contains $_.Name } |
        Sort-Object FullName -Descending |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
}

function Remove-ItemsByPattern {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string[]]$Patterns
    )

    if (-not (Test-Path $Root)) {
        return
    }

    foreach ($Pattern in $Patterns) {
        Get-ChildItem -Path $Root -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like $Pattern } |
            Sort-Object FullName -Descending |
            ForEach-Object {
                if ($_.PSIsContainer) {
                    Remove-Item -LiteralPath $_.FullName -Recurse -Force
                }
                else {
                    Remove-Item -LiteralPath $_.FullName -Force
                }
            }
    }
}

function Get-DirectoryStats {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $Files = @(Get-ChildItem -Path $Root -Recurse -File -Force -ErrorAction SilentlyContinue)
    $Bytes = ($Files | Measure-Object -Property Length -Sum).Sum

    if ($null -eq $Bytes) {
        $Bytes = 0
    }

    [PSCustomObject]@{
        Files = $Files.Count
        Bytes = [int64]$Bytes
    }
}

function Get-VenvHome {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VenvCfg
    )

    $PythonHome = (
        Get-Content $VenvCfg |
            Where-Object { $_ -like "home = *" } |
            ForEach-Object { $_.Split("=", 2)[1].Trim() } |
            Select-Object -First 1
    )

    if (-not $PythonHome -or -not (Test-Path $PythonHome)) {
        throw "Could not resolve the base Python installation from the virtual environment: $PythonHome"
    }

    return $PythonHome
}

function Ensure-BuildVenv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePython,
        [Parameter(Mandatory = $true)]
        [string]$BuildRoot,
        [Parameter(Mandatory = $true)]
        [string]$BuildVenvRoot,
        [Parameter(Mandatory = $true)]
        [string]$RequirementsFile
    )

    if (-not (Test-Path $RequirementsFile)) {
        throw "Could not find requirements.txt at $RequirementsFile"
    }

    if (-not (Test-Path $BasePython)) {
        throw "Could not find base Python executable at $BasePython"
    }

    New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null

    $Fingerprint = (Get-FileHash -Algorithm SHA256 $RequirementsFile).Hash
    $FingerprintPath = Join-Path $BuildRoot "requirements.sha256"
    $BuildPython = Join-Path $BuildVenvRoot "Scripts\python.exe"
    $ExistingFingerprint = ""

    if (Test-Path $FingerprintPath) {
        $ExistingFingerprint = (Get-Content $FingerprintPath -Raw).Trim()
    }

    if ((Test-Path $BuildPython) -and ($ExistingFingerprint -eq $Fingerprint)) {
        Write-Host "Reusing cached deployment venv at $BuildVenvRoot"
        return
    }

    Write-Host "Creating clean deployment venv at $BuildVenvRoot"
    Remove-PathIfExists $BuildVenvRoot
    & $BasePython -m venv $BuildVenvRoot

    Write-Host "Installing runtime dependencies from requirements.txt"
    & $BuildPython -m pip install --disable-pip-version-check --upgrade pip
    & $BuildPython -m pip install --disable-pip-version-check -r $RequirementsFile

    Set-Content -Path $FingerprintPath -Value $Fingerprint -Encoding ASCII
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot "desktop-runtime"
$BackendRoot = Join-Path $RuntimeRoot "backend"
$PythonRoot = Join-Path $RuntimeRoot "python"
$VenvCfg = Join-Path $ProjectRoot "venv\pyvenv.cfg"
$BuildRoot = Join-Path $ProjectRoot "build\tauri-runtime"
$BuildVenvRoot = Join-Path $BuildRoot "venv"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$SitePackagesTarget = Join-Path $PythonRoot "Lib\site-packages"

Write-Host "[1/7] Generating Tauri icons..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "tools\generate_tauri_icons.ps1")

if (-not (Test-Path $VenvCfg)) {
    throw "Could not find venv\pyvenv.cfg. Create the Python 3.11 virtual environment first."
}

$PythonHome = Get-VenvHome -VenvCfg $VenvCfg
$BasePython = Join-Path $PythonHome "python.exe"
$BuildPython = Join-Path $BuildVenvRoot "Scripts\python.exe"
Ensure-BuildVenv `
    -BasePython $BasePython `
    -BuildRoot $BuildRoot `
    -BuildVenvRoot $BuildVenvRoot `
    -RequirementsFile $RequirementsFile
$SitePackagesSource = Join-Path (Split-Path -Parent (Split-Path -Parent $BuildPython)) "Lib\site-packages"

if (-not (Test-Path $SitePackagesSource)) {
    throw "Could not find deployment site-packages at $SitePackagesSource"
}

Write-Host "[2/7] Resetting desktop runtime..."
Remove-PathIfExists $RuntimeRoot
New-Item -ItemType Directory -Path $RuntimeRoot, $BackendRoot, $PythonRoot | Out-Null

Write-Host "[3/7] Copying Python runtime..."
$PythonDirs = @("DLLs", "Lib")
$PythonFiles = @(
    "python.exe",
    "pythonw.exe",
    "python311.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)

foreach ($DirName in $PythonDirs) {
    $Source = Join-Path $PythonHome $DirName
    if (Test-Path $Source) {
        $Destination = Join-Path $PythonRoot $DirName
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
    }
}

foreach ($FileName in $PythonFiles) {
    $Source = Join-Path $PythonHome $FileName
    if (Test-Path $Source) {
        Copy-Item -Path $Source -Destination (Join-Path $PythonRoot $FileName) -Force
    }
}

Write-Host "[4/7] Copying runtime Python packages..."
Remove-PathIfExists $SitePackagesTarget
New-Item -ItemType Directory -Path $SitePackagesTarget -Force | Out-Null
Copy-Item -Path (Join-Path $SitePackagesSource "*") -Destination $SitePackagesTarget -Recurse -Force

Write-Host "[5/7] Copying backend sources..."
Copy-Item -Path (Join-Path $ProjectRoot "app") -Destination (Join-Path $BackendRoot "app") -Recurse

$LocalRagEntry = Join-Path $ProjectRoot "local_rag.py"
if (Test-Path $LocalRagEntry) {
    Copy-Item -Path $LocalRagEntry -Destination (Join-Path $BackendRoot "local_rag.py")
}

Write-Host "[6/7] Pruning caches and build-only packages..."
$DirsToRemove = @(
    "__pycache__",
    "test",
    "tests",
    "testing",
    "example",
    "examples",
    "docs",
    "doc",
    "idlelib",
    "tkinter",
    "turtledemo"
)

Remove-TreeByName -Root $RuntimeRoot -Names $DirsToRemove

$DirectPathsToRemove = @(
    (Join-Path $PythonRoot "Lib\ensurepip"),
    (Join-Path $PythonRoot "Lib\site-packages\pip"),
    (Join-Path $PythonRoot "Lib\site-packages\pkg_resources"),
    (Join-Path $PythonRoot "Lib\site-packages\setuptools"),
    (Join-Path $PythonRoot "Lib\site-packages\wheel")
)

foreach ($PathToRemove in $DirectPathsToRemove) {
    Remove-PathIfExists $PathToRemove
}

$PatternsToRemove = @(
    "*.pyc",
    "*.pyo",
    "*.whl",
    "pip-*.dist-info",
    "setuptools-*.dist-info",
    "wheel-*.dist-info"
)

Remove-ItemsByPattern -Root $RuntimeRoot -Patterns $PatternsToRemove

Write-Host "[7/7] Measuring desktop runtime..."
$Stats = Get-DirectoryStats -Root $RuntimeRoot
$SizeMb = $Stats.Bytes / 1MB

Write-Host ("Prepared desktop runtime at {0}" -f $RuntimeRoot)
Write-Host ("Runtime files: {0}; size: {1:N1} MB" -f $Stats.Files, $SizeMb)
