[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidateSet('doctor', 'collect', 'step', 'loop')][string]$Mode = 'doctor',
    [string]$RunId = '',
    [switch]$Background
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Config = [System.IO.Path]::GetFullPath($Config)
$settings = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$controller = Join-Path $PSScriptRoot 'controller.py'
$arguments = @($controller, '--config', $Config, $Mode)
if ($Mode -eq 'collect') {
    if (-not $RunId) { throw 'collect requires -RunId' }
    $arguments += @('--run-id', $RunId)
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
