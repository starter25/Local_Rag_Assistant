$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$IconsDir = Join-Path $ProjectRoot "src-tauri\icons"
$PngPath = Join-Path $IconsDir "icon.png"
$IcoPath = Join-Path $IconsDir "icon.ico"

New-Item -ItemType Directory -Path $IconsDir -Force | Out-Null

Add-Type -AssemblyName System.Drawing

$size = 256
$bitmap = New-Object System.Drawing.Bitmap $size, $size
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::FromArgb(20, 24, 33))

$backgroundRect = New-Object System.Drawing.Rectangle 0, 0, $size, $size
$gradient = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    $backgroundRect,
    ([System.Drawing.Color]::FromArgb(28, 117, 188)),
    ([System.Drawing.Color]::FromArgb(38, 171, 115)),
    45.0
)
$graphics.FillRectangle($gradient, $backgroundRect)

$haloBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(36, 255, 255, 255))
$graphics.FillEllipse($haloBrush, 30, 30, 196, 196)

$cardBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(250, 255, 255, 255))
$graphics.FillRectangle($cardBrush, 78, 56, 100, 142)

$foldPoints = @(
    (New-Object System.Drawing.Point 150, 56),
    (New-Object System.Drawing.Point 178, 84),
    (New-Object System.Drawing.Point 178, 56)
)
$graphics.FillPolygon($gradient, $foldPoints)

$linePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(28, 117, 188)), 8
$graphics.DrawLine($linePen, 96, 102, 160, 102)
$graphics.DrawLine($linePen, 96, 128, 152, 128)
$graphics.DrawLine($linePen, 96, 154, 138, 154)

$lensPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(19, 38, 76)), 14
$graphics.DrawEllipse($lensPen, 122, 128, 70, 70)
$graphics.DrawLine($lensPen, 178, 184, 214, 220)

$bitmap.Save($PngPath, [System.Drawing.Imaging.ImageFormat]::Png)

$pngBytes = [System.IO.File]::ReadAllBytes($PngPath)
$fileStream = [System.IO.File]::Open($IcoPath, [System.IO.FileMode]::Create)
$writer = New-Object System.IO.BinaryWriter($fileStream)

try {
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]1)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$pngBytes.Length)
    $writer.Write([UInt32]22)
    $writer.Write($pngBytes)
}
finally {
    $writer.Dispose()
    $fileStream.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
    $gradient.Dispose()
    $haloBrush.Dispose()
    $cardBrush.Dispose()
    $linePen.Dispose()
    $lensPen.Dispose()
}

Write-Host "Generated Tauri icons in $IconsDir"
