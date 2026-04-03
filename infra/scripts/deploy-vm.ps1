[CmdletBinding()]
param(
    [string]$VmHost = '85.211.181.183',
    [string]$VmUser = 'azureuser',
    [string]$KeyPath = '',
    [string]$EnvFile = '',
    [string]$RemoteRoot = '/srv/azure-rag-knowledge-bot'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Resolve-CommandName {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }

    throw "Required command not found. Tried: $($Candidates -join ', ')"
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Invoke-RemoteScript {
    param(
        [string[]]$SshArguments,
        [string]$ScriptText,
        [string]$FailureMessage
    )

    $normalizedScript = $ScriptText -replace "`r`n", "`n"
    $localTempScript = Join-Path $env:TEMP "codex-remote-$PID-$((Get-Random)).sh"
    $remoteTempScript = "/tmp/codex-remote-$PID-$((Get-Random)).sh"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    try {
        [System.IO.File]::WriteAllText($localTempScript, $normalizedScript, $utf8NoBom)

        $sshOptionArgs = $SshArguments[0..($SshArguments.Count - 2)]
        $sshTarget = $SshArguments[-1]

        & scp @sshOptionArgs $localTempScript "${sshTarget}:${remoteTempScript}"
        if ($LASTEXITCODE -ne 0) {
            throw $FailureMessage
        }

        & ssh @SshArguments "bash $remoteTempScript && rm -f $remoteTempScript"
        if ($LASTEXITCODE -ne 0) {
            throw $FailureMessage
        }
    }
    finally {
        Remove-Item -LiteralPath $localTempScript -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-SshKey {
    param(
        [string]$DesiredKeyPath,
        [string]$FallbackKeyPath
    )

    if (Test-Path -LiteralPath $DesiredKeyPath) {
        return (Resolve-Path -LiteralPath $DesiredKeyPath).Path
    }

    if (-not (Test-Path -LiteralPath $FallbackKeyPath)) {
        throw "SSH key not found at '$DesiredKeyPath' or '$FallbackKeyPath'."
    }

    $targetDir = Split-Path -Parent $DesiredKeyPath
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $FallbackKeyPath -Destination $DesiredKeyPath -Force

    $currentUser = whoami
    & icacls $DesiredKeyPath /inheritance:r /grant:r "${currentUser}:(R)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to tighten permissions for SSH key '$DesiredKeyPath'."
    }

    return (Resolve-Path -LiteralPath $DesiredKeyPath).Path
}

function New-ProductionEnvFile {
    param(
        [string]$SourceEnvPath,
        [string]$TempDirectory
    )

    if (-not (Test-Path -LiteralPath $SourceEnvPath)) {
        throw "Environment file not found: $SourceEnvPath"
    }

    $lines = Get-Content -LiteralPath $SourceEnvPath -Encoding UTF8
    $result = New-Object System.Collections.Generic.List[string]
    $hasAppEnv = $false

    foreach ($line in $lines) {
        if ($line -match '^\s*APP_ENV=') {
            $result.Add('APP_ENV=production')
            $hasAppEnv = $true
        }
        else {
            $result.Add($line)
        }
    }

    if (-not $hasAppEnv) {
        $result.Add('APP_ENV=production')
    }

    $tempEnvPath = Join-Path $TempDirectory "azure-rag-backend.$PID.env"
    Set-Content -LiteralPath $tempEnvPath -Value $result -Encoding UTF8
    return $tempEnvPath
}

function Wait-HttpReady {
    param(
        [string]$Uri,
        [int]$MaxAttempts = 12,
        [int]$DelaySeconds = 3
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return Invoke-RestMethod -Uri $Uri -TimeoutSec 30
        }
        catch {
            if ($attempt -eq $MaxAttempts) {
                throw
            }
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
$frontendDir = Join-Path $repoRoot 'frontend'
$backendDir = Join-Path $repoRoot 'backend'
$knowledgeDir = Join-Path $repoRoot 'docs\knowledge'
$fallbackKeyPath = Join-Path $repoRoot 'infra\vm-b1s-linux-01_key.pem'

if ([string]::IsNullOrWhiteSpace($KeyPath)) {
    $KeyPath = Join-Path $HOME '.ssh\vm-b1s-linux-01_key.pem'
}
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repoRoot '.env'
}

Assert-Command 'ssh'
Assert-Command 'scp'
Assert-Command 'python'

$npmCommand = Resolve-CommandName @('npm.cmd', 'npm')

$resolvedKeyPath = Ensure-SshKey -DesiredKeyPath $KeyPath -FallbackKeyPath $fallbackKeyPath
$resolvedEnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$sshArgs = @('-o', 'StrictHostKeyChecking=no', '-i', $resolvedKeyPath, "$VmUser@$VmHost")
$scpBaseArgs = @('-o', 'StrictHostKeyChecking=no', '-i', $resolvedKeyPath)
$tempEnvPath = $null

try {
    Write-Step 'Building frontend for the VM'
    Push-Location $frontendDir
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
            Invoke-Checked -FilePath $npmCommand -Arguments @('ci') -FailureMessage 'npm ci failed.'
        }

        $env:VITE_API_BASE_URL = '/api'
        Invoke-Checked -FilePath $npmCommand -Arguments @('run', 'build') -FailureMessage 'Frontend build failed.'
    }
    finally {
        Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
        Pop-Location
    }

    Write-Step 'Preparing production environment file'
    $tempEnvPath = New-ProductionEnvFile -SourceEnvPath $resolvedEnvFile -TempDirectory $env:TEMP

    Write-Step 'Preparing the VM runtime and application directories'
    $prepareRemoteScript = @'
set -euo pipefail

REMOTE_ROOT="__REMOTE_ROOT__"

if ! command -v nginx >/dev/null 2>&1 || ! python3 -c "import venv" >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y nginx python3-venv
fi

sudo mkdir -p "$REMOTE_ROOT"
sudo chown -R "$USER:$USER" "$REMOTE_ROOT"
find "$REMOTE_ROOT" -maxdepth 1 \( -name 'backend*' -o -name 'docs*' -o -name 'frontend-dist*' -o -name 'dist*' \) -exec rm -rf {} +
mkdir -p "$REMOTE_ROOT/backend" "$REMOTE_ROOT/docs" "$REMOTE_ROOT/frontend-dist"
'@.Replace('__REMOTE_ROOT__', $RemoteRoot)
    Invoke-RemoteScript -SshArguments $sshArgs -ScriptText $prepareRemoteScript -FailureMessage 'Failed to prepare the VM.'

    Write-Step 'Uploading backend, knowledge documents, frontend, and environment file'
    Invoke-Checked -FilePath 'scp' -Arguments ($scpBaseArgs + @('-r', (Join-Path $backendDir 'app'), (Join-Path $backendDir 'scripts'), (Join-Path $backendDir 'main.py'), (Join-Path $backendDir 'requirements.txt'), "${VmUser}@${VmHost}:${RemoteRoot}/backend/")) -FailureMessage 'Failed to upload backend files.'
    Invoke-Checked -FilePath 'scp' -Arguments ($scpBaseArgs + @('-r', $knowledgeDir, "${VmUser}@${VmHost}:${RemoteRoot}/docs/")) -FailureMessage 'Failed to upload knowledge documents.'
    Invoke-Checked -FilePath 'scp' -Arguments ($scpBaseArgs + @('-r', (Join-Path $frontendDir 'dist'), "${VmUser}@${VmHost}:${RemoteRoot}/")) -FailureMessage 'Failed to upload frontend files.'
    Invoke-Checked -FilePath 'scp' -Arguments ($scpBaseArgs + @($tempEnvPath, "${VmUser}@${VmHost}:${RemoteRoot}/.env.production")) -FailureMessage 'Failed to upload environment file.'

    Write-Step 'Configuring the backend service and nginx'
    $configureRemoteScript = @'
set -euo pipefail

REMOTE_ROOT="__REMOTE_ROOT__"

python3 -m venv "$REMOTE_ROOT/.venv"
"$REMOTE_ROOT/.venv/bin/pip" install --upgrade pip
"$REMOTE_ROOT/.venv/bin/pip" install -r "$REMOTE_ROOT/backend/requirements.txt"

if [ -d "$REMOTE_ROOT/frontend-dist/dist" ]; then
  shopt -s dotglob nullglob
  mv "$REMOTE_ROOT/frontend-dist/dist/"* "$REMOTE_ROOT/frontend-dist/"
  rmdir "$REMOTE_ROOT/frontend-dist/dist"
fi

if [ -d "$REMOTE_ROOT/dist" ]; then
  shopt -s dotglob nullglob
  mv "$REMOTE_ROOT/dist/"* "$REMOTE_ROOT/frontend-dist/"
  rmdir "$REMOTE_ROOT/dist"
fi

sudo tee /etc/systemd/system/azure-rag-backend.service >/dev/null <<'SERVICE'
[Unit]
Description=Azure RAG Knowledge Bot backend
After=network.target

[Service]
User=azureuser
Group=azureuser
WorkingDirectory=__REMOTE_ROOT__/backend
EnvironmentFile=__REMOTE_ROOT__/.env.production
ExecStart=__REMOTE_ROOT__/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo tee /etc/nginx/sites-available/azure-rag-knowledge-bot >/dev/null <<'NGINX'
server {
    listen 80;
    server_name _;

    root __REMOTE_ROOT__/frontend-dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /redoc {
        proxy_pass http://127.0.0.1:8000/redoc;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/azure-rag-knowledge-bot /etc/nginx/sites-enabled/azure-rag-knowledge-bot
sudo systemctl daemon-reload
sudo systemctl enable --now azure-rag-backend.service
sudo systemctl restart azure-rag-backend.service
sudo nginx -t
sudo systemctl restart nginx
'@.Replace('__REMOTE_ROOT__', $RemoteRoot)
    Invoke-RemoteScript -SshArguments $sshArgs -ScriptText $configureRemoteScript -FailureMessage 'Failed to configure services on the VM.'

    Write-Step 'Verifying the deployed application'
    $health = Wait-HttpReady -Uri "http://$VmHost/api/health"
    $homeResponse = Invoke-WebRequest -Uri "http://$VmHost/" -TimeoutSec 30 -UseBasicParsing

    Write-Host ''
    Write-Host 'Deployment completed.' -ForegroundColor Green
    Write-Host "Frontend : http://$VmHost/"
    Write-Host "Health   : http://$VmHost/api/health"
    Write-Host "Docs     : http://$VmHost/docs"
    Write-Host "Status   : $($health.status)"
    Write-Host "HomeCode : $($homeResponse.StatusCode)"
}
finally {
    if ($tempEnvPath -and (Test-Path -LiteralPath $tempEnvPath)) {
        Remove-Item -LiteralPath $tempEnvPath -Force
    }
}
