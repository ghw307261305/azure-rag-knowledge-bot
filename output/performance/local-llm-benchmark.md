# Local LLM Performance Benchmark

Generated at: `2026-07-13T10:05:45.921016+00:00`

## Configuration

- Model: `gemma3:4b-it-qat`
- Context length: `2048`
- Context chunks / score ratio / max chars: `2 / 0.9 / 1000`
- Max output tokens: `160`
- Threads / batch: `4 / 256`
- Keep alive: `30m`

## Summary

- Successful runs: 2 / 2
- Average wall latency: 30498 ms
- Min / max wall latency: 24076 / 36921 ms
- Average generation speed: 5.06 tok/s
- Speedup vs P4 average: 2.29x
- Quality gate: PASS

## Runs

| Run | State | Wall ms | Load ms | Prompt ms | Generate ms | tok/s | Prompt / Completion | Context | Evidence completion | Fallback |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | cold | 36921 | 12321 | 11273 | 12861 | 5.05 | 330 / 65 | 1 chunks / 106 chars | no | - |
| 2 | warm | 24076 | 330 | 10989 | 12257 | 5.06 | 323 / 62 | 1 chunks / 81 chars | no | - |
