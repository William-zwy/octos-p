[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [Parameter(Mandatory = $true)][string]$Git,
    [Parameter(Mandatory = $true)][string]$Codex,
    [Parameter(Mandatory = $true)][string]$Runtime,
    [string]$Credentials = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$Runtime = [System.IO.Path]::GetFullPath($Runtime)
if ($Runtime.StartsWith($repo.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Runtime and credentials must be outside the repository'
}
& $Python -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python' }
$gitRoot = (& $Git -C $repo rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Repository preflight failed' }
& $Python -c 'from pathlib import Path; import sys; assert Path(sys.argv[1]).resolve() == Path(sys.argv[2]).resolve(), "Wrong repository root"' $repo $gitRoot
if ($LASTEXITCODE -ne 0) { throw 'Wrong repository root' }
if (& $Git -C $repo status --porcelain=v1) { throw 'Preserve existing changes; install from a clean checkout' }
& $Git -C $repo fetch octos-p
if ($LASTEXITCODE -ne 0) { throw 'Remote preflight failed' }
& $Python -m venv $Runtime
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
$runtimePython = Join-Path $Runtime 'Scripts/python.exe'
$revision = '15b0b27da4a4a0d412c79cbfaa318c59da5c3689'
$archive = Join-Path $Runtime 'arcbench-cli-source.zip'
& $Python -c 'import urllib.request,sys; urllib.request.urlretrieve(sys.argv[1],sys.argv[2])' `
    "https://codeload.github.com/thunderstone-group/arcbench-cli/zip/$revision" $archive
if ($LASTEXITCODE -ne 0) { throw 'Pinned CLI download failed' }
& $runtimePython -m pip install --disable-pip-version-check $archive 'PyYAML==6.0.3'
if ($LASTEXITCODE -ne 0) { throw 'Runtime installation failed' }
$private = Join-Path $Runtime 'private'
New-Item -ItemType Directory -Path $private -Force | Out-Null
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $private /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private runtime ACL failed' }
$envFile = Join-Path $private 'arc.env'
if ($Credentials) {
    if (-not (Test-Path -LiteralPath $envFile)) {
        & $runtimePython (Join-Path $PSScriptRoot 'login.py') --credentials $Credentials --output $envFile
        if ($LASTEXITCODE -ne 0) { throw 'ARC login failed; no credential values were logged' }
    }
}
$configFile = Join-Path $private 'config.json'
if (Test-Path -LiteralPath $configFile) { throw 'Existing config preserved; edit it explicitly' }
$settings = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.example.json') -Raw | ConvertFrom-Json
$settings.repo = $repo
$settings.git = [System.IO.Path]::GetFullPath($Git)
$settings.python = $runtimePython
$settings.codex = [System.IO.Path]::GetFullPath($Codex)
$settings.env_file = $envFile
$settings.state_dir = Join-Path $private 'state'
$settings.branch = (& $Git -C $repo branch --show-current).Trim()
[System.IO.File]::WriteAllText($configFile, ($settings | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
$receipt = @{ cli_revision = $revision; source_zip_sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash }
[System.IO.File]::WriteAllText((Join-Path $Runtime 'install-receipt.json'), ($receipt | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Output "Installed. External config: $configFile. Paid loop remains disabled."
