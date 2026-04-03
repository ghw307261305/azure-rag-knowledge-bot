# Local Run Commands

Use two terminals for normal local development.

## First-time setup

Backend:

```powershell
.\scripts\dev-backend.ps1 -Install
```

Frontend:

```powershell
.\scripts\dev-frontend.ps1 -Install
```

## Daily local run

Backend:

```powershell
.\scripts\dev-backend.ps1
```

Frontend:

```powershell
.\scripts\dev-frontend.ps1
```

## Open both services at once

```powershell
.\scripts\dev-local.ps1
```

Use `-Install` the first time if dependencies are not installed yet:

```powershell
.\scripts\dev-local.ps1 -Install
```

## Default local URLs

- Backend API: `http://127.0.0.1:8000`
- Backend Swagger UI: `http://127.0.0.1:8000/docs`
- Frontend UI: `http://127.0.0.1:5173`

## Manual commands

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000/api"
npm run dev -- --host 127.0.0.1 --port 5173
```
