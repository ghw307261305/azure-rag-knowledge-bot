"""Benchmark cold/warm local Gemma RAG latency with stage-level metrics."""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "performance"
BASELINE_AVERAGE_MS = 69864.345
QUESTIONS = [
    "振込はいつまで取り消せますか",
    "AML アラートが出たら直ちに口座を凍結しますか",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Gemma RAG performance")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--cold-start", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-average-ms", type=float, default=70000)
    parser.add_argument("--min-tokens-per-second", type=float, default=0.5)
    args = parser.parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")

    os.environ["RAG_MODE"] = "local_llm"
    os.environ["MEMORY_ENABLED"] = "false"

    from fastapi.testclient import TestClient

    from app.services.config import get_settings
    from app.services.local_search_service import get_local_search_service
    from app.services.observability_service import get_observability_service
    from app.services.rag_service_factory import get_rag_service
    from main import app

    get_settings.cache_clear()
    get_rag_service.cache_clear()
    get_local_search_service.cache_clear()
    get_observability_service.cache_clear()
    settings = get_settings()

    if args.cold_start:
        _unload_model(settings.ollama_base_url, settings.ollama_model)

    client = TestClient(app)
    runs: list[dict] = []
    for index in range(args.runs):
        question = QUESTIONS[index % len(QUESTIONS)]
        started_at = time.perf_counter()
        response = client.post("/api/chat", json={"question": question})
        wall_ms = (time.perf_counter() - started_at) * 1000
        body = response.json()
        metrics = body.get("generation_metrics", {})
        runs.append(
            {
                "run": index + 1,
                "temperature_state": "cold" if args.cold_start and index == 0 else "warm",
                "question": question,
                "status_code": response.status_code,
                "fallback_used": body.get("fallback_used", False),
                "fallback_reason": metrics.get("fallback_reason", ""),
                "evidence_completion_used": metrics.get(
                    "evidence_completion_used", False
                ),
                "wall_ms": round(wall_ms, 3),
                "api_latency_ms": body.get("latency_ms", 0),
                "model_load_ms": metrics.get("model_load_ms", 0),
                "prompt_eval_ms": metrics.get("prompt_eval_ms", 0),
                "generation_ms": metrics.get("generation_ms", 0),
                "ollama_total_ms": metrics.get("ollama_total_ms", 0),
                "prompt_tokens": body.get("token_usage", {}).get("prompt_tokens", 0),
                "completion_tokens": body.get("token_usage", {}).get(
                    "completion_tokens", 0
                ),
                "tokens_per_second": metrics.get(
                    "generation_tokens_per_second", 0
                ),
                "context_chunks": metrics.get("context_chunks", 0),
                "context_characters": metrics.get("context_characters", 0),
                "prompt_characters": metrics.get("prompt_characters", 0),
            }
        )

    successful = [run for run in runs if not run["fallback_used"]]
    wall_times = [run["wall_ms"] for run in successful]
    speeds = [run["tokens_per_second"] for run in successful]
    average_ms = statistics.mean(wall_times) if wall_times else 0.0
    average_speed = statistics.mean(speeds) if speeds else 0.0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "model": settings.ollama_model,
            "context_length": settings.ollama_context_length,
            "max_tokens": settings.ollama_max_tokens,
            "keep_alive": settings.ollama_keep_alive,
            "context_chunks": settings.ollama_context_chunks,
            "context_score_ratio": settings.ollama_context_score_ratio,
            "max_chunk_chars": settings.ollama_max_chunk_chars,
            "num_threads": settings.ollama_num_threads,
            "num_batch": settings.ollama_num_batch,
            "cold_start": args.cold_start,
        },
        "baseline": {
            "p4_average_generation_latency_ms": BASELINE_AVERAGE_MS,
        },
        "summary": {
            "runs": len(runs),
            "successful_runs": len(successful),
            "fallback_runs": len(runs) - len(successful),
            "average_wall_ms": round(average_ms, 3),
            "min_wall_ms": round(min(wall_times), 3) if wall_times else 0.0,
            "max_wall_ms": round(max(wall_times), 3) if wall_times else 0.0,
            "average_tokens_per_second": round(average_speed, 3),
            "speedup_vs_p4_average": round(BASELINE_AVERAGE_MS / average_ms, 3)
            if average_ms
            else 0.0,
        },
        "quality_gate": {
            "max_average_ms": args.max_average_ms,
            "min_tokens_per_second": args.min_tokens_per_second,
            "passed": bool(
                len(successful) == len(runs)
                and average_ms <= args.max_average_ms
                and average_speed >= args.min_tokens_per_second
            ),
        },
        "runs": runs,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "local-llm-benchmark.json"
    markdown_path = args.output_dir / "local-llm-benchmark.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(f"Runs: {summary['successful_runs']}/{summary['runs']} successful")
    print(f"Average wall latency: {summary['average_wall_ms']:.0f} ms")
    print(f"Average generation speed: {summary['average_tokens_per_second']:.2f} tok/s")
    print(f"Speedup vs P4 average: {summary['speedup_vs_p4_average']:.2f}x")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if report["quality_gate"]["passed"] else 1


def _unload_model(base_url: str, model: str) -> None:
    try:
        httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10.0,
        ).raise_for_status()
    except httpx.HTTPError:
        pass


def _render_markdown(report: dict) -> str:
    summary = report["summary"]
    config = report["configuration"]
    gate = report["quality_gate"]
    lines = [
        "# Local LLM Performance Benchmark",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Configuration",
        "",
        f"- Model: `{config['model']}`",
        f"- Context length: `{config['context_length']}`",
        f"- Context chunks / score ratio / max chars: "
        f"`{config['context_chunks']} / {config['context_score_ratio']} / {config['max_chunk_chars']}`",
        f"- Max output tokens: `{config['max_tokens']}`",
        f"- Threads / batch: `{config['num_threads']} / {config['num_batch']}`",
        f"- Keep alive: `{config['keep_alive']}`",
        "",
        "## Summary",
        "",
        f"- Successful runs: {summary['successful_runs']} / {summary['runs']}",
        f"- Average wall latency: {summary['average_wall_ms']:.0f} ms",
        f"- Min / max wall latency: {summary['min_wall_ms']:.0f} / {summary['max_wall_ms']:.0f} ms",
        f"- Average generation speed: {summary['average_tokens_per_second']:.2f} tok/s",
        f"- Speedup vs P4 average: {summary['speedup_vs_p4_average']:.2f}x",
        f"- Quality gate: {'PASS' if gate['passed'] else 'FAIL'}",
        "",
        "## Runs",
        "",
        "| Run | State | Wall ms | Load ms | Prompt ms | Generate ms | tok/s | Prompt / Completion | Context | Evidence completion | Fallback |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for run in report["runs"]:
        lines.append(
            f"| {run['run']} | {run['temperature_state']} | {run['wall_ms']:.0f} | "
            f"{run['model_load_ms']:.0f} | {run['prompt_eval_ms']:.0f} | "
            f"{run['generation_ms']:.0f} | {run['tokens_per_second']:.2f} | "
            f"{run['prompt_tokens']} / {run['completion_tokens']} | "
            f"{run['context_chunks']} chunks / {run['context_characters']} chars | "
            f"{'yes' if run['evidence_completion_used'] else 'no'} | "
            f"{run['fallback_reason'] or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
