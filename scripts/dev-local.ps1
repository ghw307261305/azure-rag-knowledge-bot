[CmdletBinding()]
param(
  [switch]$Install,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "dev-frontend.ps1"
$frontendApiBaseUrl = "http://127.0.0.1:$BackendPort/api"

$shell = Get-Command pwsh -ErrorAction SilentlyContinue
if ($shell) {
  $shellPath = $shell.Source
}
else {
  $shellPath = (Get-Command powershell -ErrorAction Stop).Source
}

$backendArgs = @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", $backendScript,
  "-Port", $BackendPort
)

if ($Install) {
  $backendArgs += "-Install"
}

$frontendArgs = @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", $frontendScript,
  "-Port", $FrontendPort,
  "-ApiBaseUrl", $frontendApiBaseUrl
)

if ($Install) {
  $frontendArgs += "-Install"
}

Start-Process -FilePath $shellPath -WorkingDirectory $repoRoot -ArgumentList $backendArgs | Out-Null
Start-Sleep -Seconds 2
Start-Process -FilePath $shellPath -WorkingDirectory $repoRoot -ArgumentList $frontendArgs | Out-Null

Write-Host "Backend window opened on http://127.0.0.1:$BackendPort"
Write-Host "Frontend window opened on http://127.0.0.1:$FrontendPort"
