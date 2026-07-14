# Local Azure Functions Sample

This folder contains a local-only Azure Functions Python sample.

## Prerequisites

- Azure Functions Core Tools v4
- Python 3.12 or newer
- PowerShell

## Setup

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item local.settings.sample.json local.settings.json
azurite
```

Open a second PowerShell terminal in this folder:

```powershell
.\.venv\Scripts\Activate.ps1
func start
```

## Test

Health check:

```powershell
Invoke-RestMethod http://localhost:7071/api/health
```

Hello endpoint:

```powershell
Invoke-RestMethod "http://localhost:7071/api/hello?name=Rigel"
```

POST body:

```powershell
Invoke-RestMethod `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"name":"Rigel"}' `
  http://localhost:7071/api/hello
```

CSV summary from the included sample file:

```powershell
Invoke-RestMethod "http://localhost:7071/api/csv-summary?preview=3"
```

CSV summary from request body:

```powershell
$csv = Get-Content .\data\sample_sales.csv -Raw
Invoke-RestMethod `
  -Method Post `
  -ContentType "text/csv; charset=utf-8" `
  -Body $csv `
  "http://localhost:7071/api/csv-summary?preview=5"
```

The response includes row count, column names, numeric column summaries, and preview rows.
