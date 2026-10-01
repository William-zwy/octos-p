[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidateSet('doctor', 'ingest', 'collect', 'analyze', 'plan', 'context', 'step', 'loop')][string]$Mode = 'doctor',
    [string]$RunId = '',
    [string]$SourceDir = '',
    [string]$Branch = '',
    [switch]$MetadataOnly,
    [switch]$Background
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Config = [System.IO.Path]::GetFullPath($Config)
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$controller = Join-Path $PSScriptRoot 'controller.py'
$arguments = @($controller, '--config', $Config, $Mode)
if ($Mode -in @('collect', 'analyze', 'plan')) {
    if (-not $RunId) { throw "$Mode requires -RunId" }
    $arguments += @('--run-id', $RunId)
}
if ($Mode -eq 'ingest') {
    if (-not $RunId) { throw 'ingest requires -RunId' }
    if (-not $SourceDir) { throw 'ingest requires -SourceDir' }
    if (-not $MetadataOnly) { throw 'ingest requires -MetadataOnly; raw files are never copied' }
    $arguments += @('--run-id', $RunId, '--source-dir', ([System.IO.Path]::GetFullPath($SourceDir)), '--metadata-only')
}
if ($Mode -eq 'context') {
    if (-not $Branch) { throw 'context requires -Branch' }
    $arguments += @('--branch', $Branch)
}
if ($Background) {
    if ($Mode -ne 'loop') { throw 'Background is for loop only' }
    if (-not $settings.enabled) { throw 'Loop is disabled; fill budget, deadline, suite identity first' }
    # Quote each path for Start-Process on Windows; no secret values in arguments.
    $quoted = $arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }
    $process = Start-Process -FilePath $settings.python -ArgumentList $quoted -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $settings.state_dir 'loop.stdout.jsonl') `
        -RedirectStandardError (Join-Path $settings.state_dir 'loop.stderr.jsonl')
    Write-Output "Controller PID: $($process.Id)"
} else {
    & $settings.python @arguments
    exit $LASTEXITCODE
}
