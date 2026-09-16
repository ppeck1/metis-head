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

$McpGateDefaults = @{
    METIS_MCP_ENABLED = "true"
    METIS_MCP_BOH_ENABLED = "true"
    METIS_MCP_ATLAS_ENABLED = "true"
}

foreach ($Name in $McpGateDefaults.Keys) {
    if (-not (Get-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue)) {
        Set-Item -LiteralPath "Env:$Name" -Value $McpGateDefaults[$Name]
    }
}

$LocalMcpEnv = Join-Path $RepoRoot ".project\local_mcp_env.ps1"
$LocalMcpConfigLoaded = $false
if (Test-Path -LiteralPath $LocalMcpEnv) {
    . $LocalMcpEnv
    $LocalMcpConfigLoaded = $true
}

Write-Host "Metis Head repo root: $env:METIS_REPO_ROOT"
Write-Host "Metis MCP gates: global=$env:METIS_MCP_ENABLED BOH=$env:METIS_MCP_BOH_ENABLED Atlas=$env:METIS_MCP_ATLAS_ENABLED"
Write-Host "Metis local MCP config loaded: $LocalMcpConfigLoaded"
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
