# Microsoft Fabric Local Development

This repo does not contain Fabric artifacts yet. Use this setup when you want
to author Microsoft Fabric notebooks, Spark job definitions, lakehouse work, or
Fabric automation from the same local workspace.

## What local means

Microsoft Fabric does not run the full Fabric service, OneLake, or Fabric Spark
locally. Local development means:

- Edit notebooks and Spark job definitions in VS Code.
- Sync Fabric items between a Fabric workspace and a local folder.
- Run notebook or Spark code on remote Fabric compute from VS Code.
- Use the Fabric CLI and REST APIs for automation.

## Prerequisites

- VS Code.
- Python 3.10 or newer.
- A Microsoft Fabric workspace.
- Fabric capacity or trial capacity for workspace items and Git integration.
- Tenant/admin switches enabled for creating Fabric items and synchronizing
  workspace items with Git when using Git integration.
- GitHub or Azure DevOps repository access if connecting a Fabric workspace to
  source control.

Optional for Fabric User data functions:

- Azure Functions Core Tools v4.
- Azurite.

## Setup

From the repo root:

```powershell
.\scripts\dev-fabric.ps1 -Install -InstallVsCodeExtensions
```

If you also want the Fabric User data functions VS Code extension:

```powershell
.\scripts\dev-fabric.ps1 -Install -InstallVsCodeExtensions -InstallUserDataFunctionsExtension
```

The script creates `.venv-fabric/`, installs `ms-fabric-cli`, and installs the
core VS Code extensions:

- `fabric.vscode-fabric`
- `ms-toolsai.jupyter`
- `SynapseVSCode.synapse`

## Sign in

```powershell
.\.venv-fabric\Scripts\Activate.ps1
fab auth login
fab help
```

In VS Code, open the command palette and run:

- `Fabric Data Engineering: Sign In`
- `Fabric Data Engineering: Set Local Work Folder`

Use a local folder such as `fabric-work/` for downloaded workspace items.

## VS Code workflow

1. Open the Fabric Data Engineering side bar.
2. Select the target Fabric workspace.
3. Download a notebook or Spark job definition to the local work folder.
4. Edit locally in VS Code.
5. Run or debug against remote Fabric Spark compute.
6. Sync or publish changes back to the Fabric workspace.

VFS mode is also available when you want to edit workspace items as remote
files without downloading them first.

## Git workflow

For team development, connect the Fabric workspace to a GitHub or Azure DevOps
repository from Fabric workspace settings. Fabric Git integration supports
connecting, committing workspace changes, updating from Git, and disconnecting.

Keep these practical constraints in mind:

- Only supported Fabric item types can be synchronized.
- Workspace admin permission is required to connect a workspace to Git.
- Line ending normalization and service-generated metadata can create diffs.
- Use Fabric Git integration for Fabric artifacts; use normal repo Git for this
  app's backend, frontend, infra, and docs.

## Working with this RAG bot repo

Start the local app as usual:

```powershell
.\scripts\dev-local.ps1 -Install
```

Local URLs:

- Backend API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Frontend UI: `http://127.0.0.1:5173`

Fabric remote Spark compute cannot call your machine's `localhost`. If a
Fabric notebook needs to call this FastAPI backend while running remotely,
publish the backend to an accessible environment or use a secure tunnel during
development.

For the local Azure Functions sample:

```powershell
cd functions-sample
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
azurite
```

Open another terminal:

```powershell
cd functions-sample
.\.venv\Scripts\Activate.ps1
func start
```

## References

- Microsoft Fabric Data Engineering VS Code extension:
  https://learn.microsoft.com/en-us/fabric/data-engineering/setup-vs-code-extension
- Microsoft Fabric CLI:
  https://learn.microsoft.com/en-us/rest/api/fabric/articles/fabric-command-line-interface
- Microsoft Fabric Git integration:
  https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-get-started
- Microsoft Fabric Git REST API:
  https://learn.microsoft.com/en-us/rest/api/fabric/core/git
