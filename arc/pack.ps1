[CmdletBinding()]
param(
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ArcRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ArcRoot ".."))
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepoRoot "octos-arc-bundle.zip"
} else {
    $OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
}

$OutputParent = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $OutputParent -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputParent -Force | Out-Null
}

$Inputs = @(
    "main.py",
    "octos_stdio.py",
    "requirement_order.py",
    "acceptance.py",
    "guard.py",
    "llm_proxy.py",
    "codegen.py",
    "run_controls.py",
    "build_identity.py",
    "package_shape.py",
    "hooks",
    "requirements.txt",
    "arcbench_agent_runtime",
    "public-tests"
)

function Test-ExcludedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path.Replace("/", "\")
    $segments = $normalized.Split("\", [System.StringSplitOptions]::RemoveEmptyEntries)
    if ($segments -contains "__pycache__") {
        return $true
    }
    return ([System.IO.Path]::GetExtension($Path) -ieq ".pyc")
}

function Copy-InputToStaging {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$StagingRoot
    )

    $source = Join-Path $ArcRoot $RelativePath
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        if (-not (Test-ExcludedPath $RelativePath)) {
            $destination = Join-Path $StagingRoot $RelativePath
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination -Force
        }
        return
    }

    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required packaging input is missing: $RelativePath"
    }

    $files = Get-ChildItem -LiteralPath $source -Recurse -File -Force
    foreach ($file in $files) {
        $relativeFromArc = $file.FullName.Substring($ArcRoot.Length).TrimStart("\", "/")
        if (Test-ExcludedPath $relativeFromArc) {
            continue
        }
        $destination = Join-Path $StagingRoot $relativeFromArc
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
}

$stagingRoot = Join-Path $OutputParent (".octos-arc-staging-{0}-{1}" -f $PID, ([guid]::NewGuid().ToString("N")))
$temporaryZip = Join-Path $OutputParent (".octos-arc-bundle-{0}-{1}.tmp.zip" -f $PID, ([guid]::NewGuid().ToString("N")))

try {
    New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
    foreach ($input in $Inputs) {
        Copy-InputToStaging -RelativePath $input -StagingRoot $stagingRoot
    }

    $pythonCommand = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
        $pythonCommand = (Get-Command python3 -ErrorAction SilentlyContinue).Source
    }
    if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
        throw "Package gate requires python or python3"
    }
    # Python writes portable ZIP local headers; .NET on Windows can retain
    # backslashes in local headers and make Python ZIP readers reject entries.
    $zipScript = "import pathlib,sys,zipfile; root=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); files=sorted(p for p in root.rglob('*') if p.is_file()); z=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED); [z.write(p,p.relative_to(root).as_posix()) for p in files]; z.close()"
    & $pythonCommand -c $zipScript $stagingRoot $temporaryZip
    if ($LASTEXITCODE -ne 0) {
        throw "Portable ZIP creation failed"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($temporaryZip)
    try {
        $entryNames = @($archive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
    } finally {
        $archive.Dispose()
    }

    $requiredRootFiles = @(
        "main.py",
        "octos_stdio.py",
        "requirement_order.py",
        "acceptance.py",
        "guard.py",
        "llm_proxy.py",
        "codegen.py",
        "requirements.txt"
    )
    foreach ($required in $requiredRootFiles) {
        if ($entryNames -notcontains $required) {
            throw "Archive validation failed: missing root entry '$required'"
        }
    }
    foreach ($entry in $entryNames) {
        if ($entry -match "(^|/)__pycache__(/|$)" -or $entry -like "*.pyc") {
            throw "Archive validation failed: forbidden entry '$entry'"
        }
        if ($entry -like "arc/*") {
            throw "Archive validation failed: unexpected 'arc/' prefix in '$entry'"
        }
    }

    $pythonCommand = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
        $pythonCommand = (Get-Command python3 -ErrorAction SilentlyContinue).Source
    }
    if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
        throw "Package gate requires python or python3"
    }
    $sourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
    if ($sourceCommit -notmatch "^[0-9a-fA-F]{40}$") {
        throw "Package gate could not resolve a full source commit"
    }
    $taskKey = if (-not [string]::IsNullOrWhiteSpace($env:ARCBENCH_TASK_KEY)) {
        $env:ARCBENCH_TASK_KEY
    } else {
        $env:ARCBENCH_TASK
    }
    $suiteKey = if (-not [string]::IsNullOrWhiteSpace($env:ARCBENCH_TEST_SUITE_KEY)) {
        $env:ARCBENCH_TEST_SUITE_KEY
    } else {
        $env:ARCBENCH_SUITE_KEY
    }
    $requirementsSha = if (-not [string]::IsNullOrWhiteSpace($env:ARCBENCH_REQUIREMENTS_SHA256)) {
        $env:ARCBENCH_REQUIREMENTS_SHA256
    } else {
        $env:ARCBENCH_REQUIREMENTS_HASH
    }
    if ([string]::IsNullOrWhiteSpace($taskKey) -or
        [string]::IsNullOrWhiteSpace($suiteKey) -or
        [string]::IsNullOrWhiteSpace($requirementsSha)) {
        throw "Package gate requires ARCBENCH_TASK_KEY, ARCBENCH_TEST_SUITE_KEY and ARCBENCH_REQUIREMENTS_SHA256"
    }
    & $pythonCommand (Join-Path $ArcRoot "build_identity.py") embed --archive $temporaryZip --commit $sourceCommit | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Build identity gate failed"
    }

    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }
    Move-Item -LiteralPath $temporaryZip -Destination $OutputPath -Force

    $shapePath = [System.IO.Path]::ChangeExtension($OutputPath, "shape.json")
    $bindingPath = [System.IO.Path]::ChangeExtension($OutputPath, "binding.json")
    & $pythonCommand (Join-Path $ArcRoot "package_gate.py") bind --archive $OutputPath --shape-output $shapePath --output $bindingPath --source-commit $sourceCommit --task-key $taskKey --suite-key $suiteKey --requirements-sha256 $requirementsSha
    if ($LASTEXITCODE -ne 0) {
        throw "Package shape/binding gate failed"
    }

    $hash = (& $pythonCommand -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest().upper())" $OutputPath).Trim()
    $size = (Get-Item -LiteralPath $OutputPath).Length
    Write-Host "Packaging complete: $OutputPath"
    Write-Host ("Entries: {0}" -f $entryNames.Count)
    Write-Host ("Bytes:   {0}" -f $size)
    Write-Host ("SHA256:  {0}" -f $hash)
} finally {
    if (Test-Path -LiteralPath $temporaryZip) {
        Remove-Item -LiteralPath $temporaryZip -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
