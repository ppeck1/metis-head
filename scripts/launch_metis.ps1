param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8787,
    [string]$PythonExe = "python",
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

Set-Location -LiteralPath $RepoRoot

if (-not $env:METIS_REPO_ROOT) {
    $env:METIS_REPO_ROOT = $RepoRoot
}

Write-Host "Metis Head repo root: $env:METIS_REPO_ROOT"
Write-Host "Starting Metis Head mock Brain at http://$HostAddress`:$Port"

$arguments = @(
    "-m",
    "uvicorn",
    "metis_head.brain:app",
    "--host",
    $HostAddress,
    "--port",
    [string]$Port
)

if ($Reload) {
    $arguments += "--reload"
}

& $PythonExe @arguments
