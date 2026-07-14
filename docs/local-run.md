# Local Run Commands

Use two terminals for normal local development.

## Runtime mode

The backend defaults to `RAG_MODE=mock` when the variable is omitted, so Azure credentials are not required for local startup or tests. The sample environment file selects `local_llm` mode, `KNOWLEDGE_DIR=docs/knowledge-finance`, and `OLLAMA_MODEL=gemma3:4b-it-qat`.

Copy the sample environment file before the first run:

```powershell
Copy-Item .env.example .env
```

Use `RAG_MODE=local_llm` for fully local retrieval and Gemma answer generation, `RAG_MODE=local` for retrieval-only inspection, or `RAG_MODE=mock` for fixed test data. Set `RAG_MODE=azure` only when valid Azure OpenAI and Azure AI Search settings are available.

`local` and `local_llm` support these endpoints without cloud access:

- `POST /api/chat`: generates a grounded answer in `local_llm`, or returns source text in `local`
- `GET /api/search/debug?q=...`: shows ranked local chunks and scores
- `POST /api/index/rebuild`: reloads Markdown files from `KNOWLEDGE_DIR`

To switch back to the previous recruitment sample, set `KNOWLEDGE_DIR=docs/knowledge` and restart the backend.

## P3: prepare Ollama and Gemma

Verify that Ollama is running and the model is installed:

```powershell
ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

If PowerShell cannot find `ollama`, use the installed executable directly or add its directory to `PATH`:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
```

If the model is not listed:

```powershell
ollama pull gemma3:4b-it-qat
```

Start the backend, then verify the complete RAG path:

```powershell
$body = @{ question = "振込はいつまで取り消せますか" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/chat `
  -Method Post -ContentType "application/json; charset=utf-8" -Body $body
```

The response should contain `rag_mode=local_llm`, `model=gemma3:4b-it-qat`, `fallback_used=false`, non-zero token counts, citations, and `[S1]`-style source markers in the answer. The first request can take longer while the model is loaded into memory.

## Run the P2 retrieval evaluation

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_retrieval.py
```

Reports are written to `output/evaluation/`. The command returns a non-zero exit code when a quality gate fails.

## Run the P4 generation evaluation

Ollama must be running. The full run sends eight real generation requests and can take several minutes on CPU-only machines.

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py
```

For a shorter smoke run:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py --max-answer-cases 2
```

Reports are written to `output/evaluation/finance-generation-report.json` and `.md`. See `docs/generation-evaluation.md` for metrics, quality gates, and the report-reuse command.

## P5: verify governed conversation memory

Start the normal local app, then submit a request with stable client and conversation IDs:

```powershell
$body = @{
  question = "请用中文简洁回答。我的邮箱是 alice@example.com。振込はいつまで取り消せますか"
  client_id = "local-browser-001"
  conversation_id = "conversation-001"
} | ConvertTo-Json

$response = Invoke-RestMethod http://127.0.0.1:8000/api/chat `
  -Method Post -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))

$response.sanitized_question
$response.memory_usage
```

The sanitized question should contain `[EMAIL]`; memory usage should report two stored preferences and `masked_pii=email`. Inspect and delete the governed memory:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/memory?client_id=local-browser-001"
Invoke-RestMethod "http://127.0.0.1:8000/api/memory?client_id=local-browser-001" -Method Delete
```

The frontend `Memory` button provides the same inspection and deletion controls. See `docs/conversation-memory-governance.md` for data boundaries and limitations.

## P6: benchmark and observe the local LLM

The default P6 settings reduce the Ollama context to 2,048 tokens, pass the strongest chunk plus at most one near-tied chunk (score at least 90% of the top result), cap each chunk at 1,000 characters and the answer at 160 tokens, use four threads with a batch size of 256, and keep the model loaded for 30 minutes.

Run one cold request followed by one warm request:

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\benchmark_local_llm.py --runs 2 --cold-start
```

Reports are written to `output/performance/local-llm-benchmark.json` and `.md`. The command fails its quality gate when a request falls back, average latency exceeds 70 seconds, or generation speed is below 0.5 token/s.

While the backend is running, inspect accumulated chat metrics and the current machine/Ollama state:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/observability
```

Reset only the in-memory metric samples:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/observability -Method Delete
```

Keeping the model loaded avoids repeated load time but retains about the model's full memory allocation. During memory-sensitive development work, unload it explicitly:

```powershell
$body = @{ model = "gemma3:4b-it-qat"; keep_alive = 0 } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11434/api/generate `
  -Method Post -ContentType "application/json" -Body $body
```

See `docs/performance-observability.md` for metric definitions, tuning decisions, and limitations.

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
