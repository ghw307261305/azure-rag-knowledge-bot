# P6: Local LLM Performance and Observability

## Goal

P6 makes the CPU-only Gemma path measurable and reduces avoidable latency without weakening the existing grounded-answer and citation checks.

The P4 baseline on this machine was:

- Average generation latency: `69,864 ms`
- P95 generation latency: `131,498 ms`
- Runtime: Intel Core i5-10210U, 4 physical / 8 logical cores, about 15.8 GB RAM
- Model: `gemma3:4b-it-qat`, about 3.55 GB, CPU-only

## Tuning applied

| Setting | P6 value | Purpose |
|---|---:|---|
| `OLLAMA_CONTEXT_LENGTH` | 2048 | Reduce attention and prompt memory cost |
| `OLLAMA_CONTEXT_CHUNKS` | 2 | Allow one additional near-tied result |
| `OLLAMA_CONTEXT_SCORE_RATIO` | 0.90 | Exclude secondary results below 90% of the top score |
| `OLLAMA_MAX_CHUNK_CHARS` | 1000 | Prevent oversized source chunks |
| `OLLAMA_MAX_TOKENS` | 160 | Bound answer generation time |
| `OLLAMA_NUM_THREADS` | 4 | Match the physical CPU core count |
| `OLLAMA_NUM_BATCH` | 256 | Balance prompt throughput and memory use |
| `OLLAMA_KEEP_ALIVE` | 30m | Avoid loading the model again between normal chats |

Retrieval still returns up to five chunks for inspection. The P4 score distribution showed weak secondary matches could distract the 4B model, while one case required a nearly tied second chunk. Gemma therefore receives the top chunk and only a second result whose score is at least 90% of the top score. Citation validation and safe fallback remain mandatory; tune the ratio only together with a P4 rerun.

## Per-response metrics

Every `POST /api/chat` response now includes `generation_metrics`:

- Context chunks and characters
- Prompt characters
- Model load, prompt evaluation, generation, and Ollama total time
- Prompt and generation tokens per second
- Ollama completion reason
- Explicit fallback reason
- Whether deterministic evidence completion appended one exact source sentence

The frontend development panel shows the high-value subset next to each assistant response.

## Runtime monitoring

`GET /api/observability` returns:

- Average, P50, and P95 end-to-end latency
- Fallback count, rate, and grouped reasons
- Evidence-completion count and rate
- Average model load, prompt evaluation, and generation time
- Average generation tokens per second
- Current system, backend, and Ollama CPU/RAM state
- Loaded model size, VRAM use, context length, and expiry time

The service stores at most 500 samples and exposes the latest 10. Data is process-local and resets after restart; `DELETE /api/observability` clears it manually.

## Benchmark

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\benchmark_local_llm.py --runs 2 --cold-start
```

The first request is measured after unloading the model; the following request measures the warm path. Reports are written to `output/performance/` and include configuration, stage timings, token throughput, fallback state, and speedup against the P4 average.

Default quality gates are:

- All runs complete without fallback
- Average wall latency is at most 70 seconds
- Average generation speed is at least 0.5 token/s

## Verified P6 result

The final full P4 rerun after P6 passed all 16 cases. For its eight real Gemma generations:

| Metric | P4 baseline | P6 final | Reduction |
|---|---:|---:|---:|
| Average latency | 69,864 ms | 23,303 ms | 66.6% |
| P95 latency | 131,498 ms | 32,263 ms | 75.5% |

Grounded concepts, numeric grounding, citation validity/coverage, refusal accuracy, and safety blocking were all 100%. The report is `output/evaluation/finance-generation-report.md`.

The final two-run cold/warm benchmark also passed its gate:

| State | Wall latency | Model load | Prompt evaluation | Generation |
|---|---:|---:|---:|---:|
| Cold | 36,921 ms | 12,321 ms | 11,273 ms | 12,861 ms |
| Warm | 24,076 ms | 330 ms | 10,989 ms | 12,257 ms |

Average wall latency was 30,498 ms, average generation speed was 5.06 tokens/s, and the measured speedup against the P4 average was 2.29x. Both runs completed without fallback or evidence completion. The report is `output/performance/local-llm-benchmark.md`.

Gemma 4B sometimes stops after a direct one-sentence answer even when the source contains another mandatory condition. P6 therefore adds a deterministic guard: only for short answers, it appends one uncovered sentence copied from the retrieved evidence. Numeric answers preferentially use the source that contains the same number. This does not invoke the model again, and its use is exposed as `evidence_completion_used`.

## Operational trade-off

Warm latency is preferred for interactive use, so the model remains loaded for 30 minutes. This consumes several GB of RAM. On a 16 GB development machine, unload the model before memory-heavy builds or unrelated work:

```powershell
$body = @{ model = "gemma3:4b-it-qat"; keep_alive = 0 } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11434/api/generate `
  -Method Post -ContentType "application/json" -Body $body
```

## Remaining limits

- CPU-only generation will still be materially slower than GPU inference.
- Two benchmark prompts are suitable for regression detection, not capacity planning.
- In-process metrics are not persistent and are not aggregated across multiple workers.
- CPU percentage is a point-in-time sample. The repo now includes a Prometheus endpoint, optional OTLP tracing, and a local Collector/Prometheus/Grafana profile; production retention, dashboards, alerting, and multi-worker aggregation remain environment-specific.
- Further latency reduction should compare a smaller model or GPU before cutting context or output enough to damage groundedness.
