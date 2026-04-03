[CmdletBinding()]
param(
  [switch]$Install,
  [int]$Port = 5173,
  [string]$ApiBaseUrl = "http://127.0.0.1:8000/api"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue

if (-not $npmCommand) {
  $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}

if (-not (Test-Path $frontendDir)) {
  throw "Frontend directory was not found: $frontendDir"
}

if (-not $npmCommand) {
  throw "npm was not found in PATH."
}

Push-Location $frontendDir
try {
  if ($Install -or -not (Test-Path "node_modules")) {
    & $npmCommand.Source install
  }

  $env:VITE_API_BASE_URL = $ApiBaseUrl

  Write-Host "Frontend is starting on http://127.0.0.1:$Port"
  Write-Host "Using API base URL: $ApiBaseUrl"

  & $npmCommand.Source run dev -- --host 127.0.0.1 --port $Port
}
finally {
  Pop-Location
}
