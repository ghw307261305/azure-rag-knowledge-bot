"""In-process chat metrics and local runtime resource snapshots."""

from __future__ import annotations

import math
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx
import psutil

from app.models.chat import ChatResponse
from app.services.config import get_settings


class ObservabilityService:
    def __init__(self, max_samples: int = 500) -> None:
        self._samples: deque[dict[str, Any]] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def record(self, response: ChatResponse) -> None:
        metrics = response.generation_metrics
        sample = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rag_mode": response.rag_mode,
            "model": response.model,
            "latency_ms": response.latency_ms,
            "fallback_used": response.fallback_used,
            "fallback_reason": metrics.fallback_reason,
            "evidence_completion_used": metrics.evidence_completion_used,
            "model_load_ms": metrics.model_load_ms,
            "prompt_eval_ms": metrics.prompt_eval_ms,
            "generation_ms": metrics.generation_ms,
            "ollama_total_ms": metrics.ollama_total_ms,
            "tokens_per_second": metrics.generation_tokens_per_second,
            "prompt_tokens": response.token_usage.prompt_tokens,
            "completion_tokens": response.token_usage.completion_tokens,
            "context_chunks": metrics.context_chunks,
            "context_characters": metrics.context_characters,
        }
        with self._lock:
            self._samples.append(sample)

    def reset(self) -> int:
        with self._lock:
            count = len(self._samples)
            self._samples.clear()
        return count

    def summary(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        latencies = sorted(float(sample["latency_ms"]) for sample in samples)
        generated = [
            sample for sample in samples if float(sample["generation_ms"]) > 0
        ]
        fallback_reasons = Counter(
            sample["fallback_reason"]
            for sample in samples
            if sample["fallback_reason"]
        )
        return {
            "sample_count": len(samples),
            "generated_count": len(generated),
            "fallback_count": sum(bool(s["fallback_used"]) for s in samples),
            "fallback_rate": _rate(
                sum(bool(s["fallback_used"]) for s in samples), len(samples)
            ),
            "fallback_reasons": dict(sorted(fallback_reasons.items())),
            "evidence_completion_count": sum(
                bool(sample["evidence_completion_used"]) for sample in samples
            ),
            "evidence_completion_rate": _rate(
                sum(bool(sample["evidence_completion_used"]) for sample in samples),
                len(samples),
            ),
            "average_latency_ms": _average(latencies),
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "average_model_load_ms": _average(
                [float(sample["model_load_ms"]) for sample in generated]
            ),
            "average_prompt_eval_ms": _average(
                [float(sample["prompt_eval_ms"]) for sample in generated]
            ),
            "average_generation_ms": _average(
                [float(sample["generation_ms"]) for sample in generated]
            ),
            "average_generation_tokens_per_second": _average(
                [float(sample["tokens_per_second"]) for sample in generated]
            ),
            "recent": samples[-10:],
        }

    def resource_snapshot(self) -> dict[str, Any]:
        process = psutil.Process()
        memory = psutil.virtual_memory()
        ollama_processes = []
        for item in psutil.process_iter(
            ["pid", "name", "memory_info", "cpu_percent"]
        ):
            try:
                name = str(item.info.get("name") or "")
                if "ollama" not in name.lower():
                    continue
                memory_info = item.info.get("memory_info")
                ollama_processes.append(
                    {
                        "pid": item.info["pid"],
                        "name": name,
                        "rss_mb": round(
                            float(memory_info.rss) / 1024 / 1024
                            if memory_info
                            else 0.0,
                            2,
                        ),
                        "cpu_percent": float(item.info.get("cpu_percent") or 0),
                    }
                )
            except (psutil.Error, OSError):
                continue
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "memory_total_gb": round(memory.total / 1024**3, 2),
                "memory_available_gb": round(memory.available / 1024**3, 2),
                "memory_percent": memory.percent,
            },
            "backend": {
                "pid": process.pid,
                "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent(interval=None),
            },
            "ollama": {
                "processes": ollama_processes,
                "loaded_models": _get_loaded_models(),
            },
        }


def _get_loaded_models() -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/ps", timeout=2.0
        )
        response.raise_for_status()
        models = response.json().get("models", [])
        return [
            {
                "name": model.get("name", ""),
                "size_gb": round(float(model.get("size") or 0) / 1024**3, 2),
                "size_vram_gb": round(
                    float(model.get("size_vram") or 0) / 1024**3, 2
                ),
                "context_length": model.get("context_length", 0),
                "expires_at": model.get("expires_at", ""),
            }
            for model in models
        ]
    except (httpx.HTTPError, ValueError, TypeError):
        return []


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(len(values) * percentile) - 1)
    return round(values[index], 3)


@lru_cache
def get_observability_service() -> ObservabilityService:
    return ObservabilityService()
