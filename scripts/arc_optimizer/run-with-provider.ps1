[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [ValidateSet('doctor', 'ingest', 'collect', 'analyze', 'plan', 'context', 'reconcile', 'approve', 'step', 'loop')][string]$Mode = 'doctor',
    [string]$RunId = '',
    [string]$SourceDir = '',
    [string]$Branch = '',
    [string]$ApiKeyFile = '',
    [switch]$MetadataOnly,
    [switch]$Background
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$repo = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot '../..'))
$configPath = [System.IO.Path]::GetFullPath($Config)
$start = Join-Path $scriptRoot 'start.ps1'
$key = $null
$secure = $null
$ptr = [IntPtr]::Zero

function Assert-ExternalPath([string]$Path, [string]$Label) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $repoPrefix = $repo.TrimEnd('\') + '\'
    if ($full.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or
        $full.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must be outside the repository"
    }
    return $full
}

try {
    if ($ApiKeyFile) {
        $keyPath = Assert-ExternalPath $ApiKeyFile 'ApiKeyFile'
        if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
            throw "ApiKeyFile does not exist: $keyPath"
        }
        $content = (Get-Content -LiteralPath $keyPath -Raw -ErrorAction Stop).Trim()
        if ($content -match '^RELAY_API_KEY=(.+)$') {
            $key = $Matches[1].Trim()
        } else {
            $key = $content
        }
    } else {
        $secure = Read-Host -Prompt '中转 API Key' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    if ([string]::IsNullOrWhiteSpace($key) -or $key -match '[\r\n]') {
        throw 'A non-empty single-line API key is required'
    }

    $env:RELAY_API_KEY = $key
    $forward = @('-Config', $configPath, '-Mode', $Mode)
    if ($RunId) { $forward += @('-RunId', $RunId) }
    if ($SourceDir) { $forward += @('-SourceDir', $SourceDir) }
    if ($Branch) { $forward += @('-Branch', $Branch) }
    if ($MetadataOnly) { $forward += '-MetadataOnly' }
    if ($Background) { $forward += '-Background' }
    & $start @forward
    exit $LASTEXITCODE
} finally {
    Remove-Item Env:RELAY_API_KEY -ErrorAction SilentlyContinue
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    if ($secure) { Remove-Variable secure -ErrorAction SilentlyContinue }
    if ($key) { Remove-Variable key -ErrorAction SilentlyContinue }
}
