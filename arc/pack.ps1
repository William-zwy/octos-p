[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$arcRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$workspaceRoot = [System.IO.Directory]::GetParent($arcRoot).FullName
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $workspaceRoot "octos-arc-bundle.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path (Get-Location).Path $OutputPath
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

$bundleItems = @(
    "main.py",
    "octos_stdio.py",
    "requirement_order.py",
    "acceptance.py",
    "repair_context.py",
    "guard.py",
    "llm_proxy.py",
    "codegen.py",
    "hooks",
    "requirements.txt",
    "arcbench_agent_runtime",
    "public-tests"
)

foreach ($item in $bundleItems) {
    $source = Join-Path $arcRoot $item
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing bundle item: $source"
    }
}

$outputParent = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputParent)) {
    New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
}
if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = $null
$entryCount = 0
try {
    $archive = [System.IO.Compression.ZipFile]::Open(
        $OutputPath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )

    foreach ($item in $bundleItems) {
        $source = Join-Path $arcRoot $item
        $sourceInfo = Get-Item -LiteralPath $source
        if ($sourceInfo.PSIsContainer) {
            $files = Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object {
                $_.FullName -notmatch "([\\/])__pycache__([\\/])" -and
                $_.Extension -ne ".pyc"
            }
            foreach ($file in $files) {
                $entryName = $file.FullName.Substring($arcRoot.Length + 1).Replace("\", "/")
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $file.FullName,
                    $entryName,
                    [System.IO.Compression.CompressionLevel]::Optimal
                ) | Out-Null
                $entryCount++
            }
        } else {
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $source,
                $item.Replace("\", "/"),
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $entryCount++
        }
    }
} finally {
    if ($null -ne $archive) {
        $archive.Dispose()
    }
}

$fileInfo = Get-Item -LiteralPath $OutputPath
$hash = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
Write-Host "Bundle created: $($fileInfo.FullName)"
Write-Host "Size: $($fileInfo.Length) bytes"
Write-Host "Entries: $entryCount"
Write-Host "SHA256: $hash"
