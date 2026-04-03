[CmdletBinding()]
param(
  [switch]$Install,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $backendDir)) {
  throw "Backend directory was not found: $backendDir"
}

Push-Location $backendDir
try {
  if (-not (Test-Path $venvPython)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    $python = Get-Command python -ErrorAction SilentlyContinue

    if ($py) {
      & $py.Source -3 -m venv .venv
    }
    elseif ($python) {
      & $python.Source -m venv .venv
    }
    else {
      throw "Python 3 was not found in PATH."
    }
  }

  if ($Install -or -not (Test-Path (Join-Path $venvDir "Lib\site-packages\fastapi"))) {
    & $venvPython -m pip install -r requirements.txt
  }

  Write-Host "Backend is starting on http://127.0.0.1:$Port"
  Write-Host "Swagger UI: http://127.0.0.1:$Port/docs"

  & $venvPython -m uvicorn main:app --host 127.0.0.1 --port $Port --reload
}
finally {
  Pop-Location
}
