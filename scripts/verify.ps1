[CmdletBinding()]
param(
    [switch]$SkipEvaluation
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Backend virtual environment was not found. Run scripts\dev-backend.ps1 -Install first.'
}

Push-Location (Join-Path $repoRoot 'backend')
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    if (-not $SkipEvaluation) {
        & $python -X utf8 scripts\evaluate_local_retrieval.py
        if ($LASTEXITCODE -ne 0) { throw 'Retrieval quality gate failed.' }
    }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $repoRoot 'frontend')
try {
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
finally {
    Pop-Location
}

& az bicep build --file (Join-Path $repoRoot 'infra\bicep\main.bicep') --stdout 1>$null
if ($LASTEXITCODE -ne 0) { throw 'Bicep validation failed.' }

Write-Host 'All local verification checks passed.' -ForegroundColor Green
