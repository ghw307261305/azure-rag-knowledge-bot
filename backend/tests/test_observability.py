from app.models.chat import ChatResponse, GenerationMetrics, TokenUsage
from app.services.observability_service import ObservabilityService


def test_observability_aggregates_latency_speed_and_fallback_reasons() -> None:
    service = ObservabilityService()
    service.record(
        ChatResponse(
            answer="ok",
            citations=[],
            retrieved_chunks=[],
            latency_ms=1000,
            token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
            rag_mode="local_llm",
            model="gemma3:4b-it-qat",
            generation_metrics=GenerationMetrics(
                model_load_ms=200,
                prompt_eval_ms=300,
                generation_ms=500,
                generation_tokens_per_second=20,
                evidence_completion_used=True,
            ),
        )
    )
    service.record(
        ChatResponse(
            answer="fallback",
            citations=[],
            retrieved_chunks=[],
            latency_ms=100,
            fallback_used=True,
            generation_metrics=GenerationMetrics(
                fallback_reason="insufficient_retrieval"
            ),
        )
    )

    summary = service.summary()
    assert summary["sample_count"] == 2
    assert summary["generated_count"] == 1
    assert summary["fallback_rate"] == 0.5
    assert summary["fallback_reasons"] == {"insufficient_retrieval": 1}
    assert summary["p50_latency_ms"] == 100.0
    assert summary["p95_latency_ms"] == 1000.0
    assert summary["average_generation_tokens_per_second"] == 20.0
    assert summary["evidence_completion_count"] == 1
    assert summary["evidence_completion_rate"] == 0.5
    assert service.reset() == 2
    assert service.summary()["sample_count"] == 0
