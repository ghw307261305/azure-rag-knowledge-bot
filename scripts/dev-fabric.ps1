[CmdletBinding()]
param(
  [switch]$Install,
  [switch]$InstallVsCodeExtensions,
  [switch]$InstallUserDataFunctionsExtension
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $repoRoot ".venv-fabric"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$fabricCli = Join-Path $venvDir "Scripts\fab.exe"

function New-FabricVenv {
  $py = Get-Command py -ErrorAction SilentlyContinue
  $python = Get-Command python -ErrorAction SilentlyContinue

  if ($py) {
    & $py.Source -3 -m venv $venvDir
    return
  }

  if ($python) {
    & $python.Source -m venv $venvDir
    return
  }

  throw "Python 3.10 or newer was not found in PATH."
}

function Resolve-CodeCommand {
  $candidates = @()

  if ($env:LOCALAPPDATA) {
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Microsoft VS Code\bin\code.cmd"
  }

  $codeCmd = Get-Command code.cmd -ErrorAction SilentlyContinue
  if ($codeCmd) {
    $candidates += $codeCmd.Source
  }

  foreach ($candidate in $candidates | Select-Object -Unique) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  throw "VS Code CLI code.cmd was not found. Open VS Code and run 'Shell Command: Install code command in PATH', or install extensions manually."
}

function Install-CodeExtension {
  param([string]$ExtensionId)

  $codeCommand = Resolve-CodeCommand
  Write-Host "Installing VS Code extension: $ExtensionId"
  & $codeCommand --install-extension $ExtensionId
}

if (-not (Test-Path $venvPython)) {
  Write-Host "Creating Fabric CLI virtual environment at $venvDir"
  New-FabricVenv
}

if ($Install -or -not (Test-Path $fabricCli)) {
  Write-Host "Installing Microsoft Fabric CLI into $venvDir"
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install --upgrade ms-fabric-cli
}

if ($InstallVsCodeExtensions) {
  Install-CodeExtension "fabric.vscode-fabric"
  Install-CodeExtension "ms-toolsai.jupyter"
  Install-CodeExtension "SynapseVSCode.synapse"

  if ($InstallUserDataFunctionsExtension) {
    Install-CodeExtension "fabric.vscode-fabric-functions"
  }
}

if (-not (Test-Path $fabricCli)) {
  throw "Fabric CLI was not found after setup: $fabricCli"
}

Write-Host ""
Write-Host "Fabric local tooling is ready."
Write-Host "Activate CLI environment:"
Write-Host "  .\.venv-fabric\Scripts\Activate.ps1"
Write-Host "Sign in to Fabric:"
Write-Host "  fab auth login"
Write-Host "Show CLI help:"
Write-Host "  fab help"
