"""ローカル検索結果を Gemma に渡す、完全ローカルの RAG サービス。"""

import logging
import re
import time

from app.models.chat import ChatResponse, Citation, GenerationMetrics, TokenUsage
from app.services.config import get_settings
from app.services.local_rag_service import (
    LOCAL_FALLBACK_ANSWER,
    _build_extractive_answer,
    _build_retrieved_chunks,
    _elapsed_ms,
)
from app.services.local_search_service import get_local_search_service
from app.services.ollama_service import (
    OllamaError,
    OllamaInvalidResponseError,
    OllamaUnavailableError,
    generate_grounded_answer,
)

logger = logging.getLogger(__name__)


class LocalLlmRagService:
    """ローカル知識ベースで検索し、Ollama 上の Gemma で回答を生成する。"""

    def answer(
        self,
        question: str,
        *,
        memory_context: str = "",
        access_groups: set[str] | None = None,
    ) -> ChatResponse:
        """ローカル検索、文脈絞り込み、Ollama 生成、安全な降格を順に実行する。"""
        started_at = time.perf_counter()
        settings = get_settings()
        results = get_local_search_service().search(
            question,
            top_k=settings.top_k,
            allowed_groups=access_groups,
        )
        top_score = results[0]["score"] if results else 0.0

        if not results or top_score < settings.local_min_score:
            return ChatResponse(
                answer=LOCAL_FALLBACK_ANSWER,
                citations=[],
                retrieved_chunks=[],
                latency_ms=_elapsed_ms(started_at),
                rewritten_query=question,
                token_usage=TokenUsage(),
                rag_mode="local_llm",
                model=settings.ollama_model,
                fallback_used=True,
                generation_metrics=GenerationMetrics(
                    fallback_reason="insufficient_retrieval"
                ),
            )

        # 小型モデルへ渡す量を制限し、最上位から大きく劣る根拠は除外する。
        context_limit = min(settings.max_chunks, settings.ollama_context_chunks)
        context_chunks = [
            chunk
            for index, chunk in enumerate(results[:context_limit])
            if index == 0
            or chunk["score"] >= top_score * settings.ollama_context_score_ratio
        ]
        context_chunks = [
            {**chunk, "content": chunk["content"][: settings.ollama_max_chunk_chars]}
            for chunk in context_chunks
        ]
        fallback_used = False
        try:
            answer, token_usage, generation_metrics = generate_grounded_answer(
                question, context_chunks, memory_context=memory_context
            )
            answer, completion_used = _complete_short_answer(answer, context_chunks)
            generation_metrics.evidence_completion_used = completion_used
        except OllamaError as exc:
            # 生成障害を API 全体の障害にせず、検索済み原文へ安全に降格する。
            logger.warning("Local generation failed; using extractive fallback: %s", exc)
            answer = _build_extractive_answer(
                context_chunks[0], generation_failed=True
            )
            token_usage = TokenUsage()
            if isinstance(exc, OllamaInvalidResponseError):
                fallback_reason = "invalid_model_response"
            elif isinstance(exc, OllamaUnavailableError):
                fallback_reason = "ollama_unavailable"
            else:
                fallback_reason = "generation_error"
            generation_metrics = GenerationMetrics(
                context_chunks=len(context_chunks),
                context_characters=sum(
                    len(chunk["content"]) for chunk in context_chunks
                ),
                fallback_reason=fallback_reason,
            )
            fallback_used = True

        return ChatResponse(
            answer=answer,
            citations=_build_numbered_citations(context_chunks),
            retrieved_chunks=_build_retrieved_chunks(results),
            latency_ms=_elapsed_ms(started_at),
            rewritten_query=question,
            token_usage=token_usage,
            rag_mode="local_llm",
            model=settings.ollama_model,
            fallback_used=fallback_used,
            generation_metrics=generation_metrics,
        )


def _build_numbered_citations(chunks: list[dict]) -> list[Citation]:
    """プロンプト内の S 番号と API の引用順序を一致させる。"""
    return [
        Citation(
            title=f"[S{index}] {chunk['source']} / {chunk['section']}",
            chunk_id=chunk["chunk_id"],
            content=chunk["content"][:500],
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _complete_short_answer(answer: str, chunks: list[dict]) -> tuple[str, bool]:
    """小型モデルの回答が短すぎる場合だけ、根拠から一文を補完する。"""
    plain_answer = re.sub(r"\[S\d+\]", "", answer).strip()
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?])\s*|\n+", plain_answer)
        if part.strip()
    ]
    if len(sentences) >= 2 or len(plain_answer) >= 80:
        return answer, False

    answer_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", plain_answer))
    candidates: list[tuple[int, str]] = []
    for source_id, chunk in enumerate(chunks, start=1):
        for line in chunk["content"].splitlines():
            if line.lstrip().startswith("#"):
                continue
            for sentence in re.split(r"(?<=[。！？!?])\s*", line.strip()):
                cleaned = sentence.strip().lstrip("-* ").strip()
                if len(cleaned) >= 10:
                    candidates.append((source_id, cleaned))

    if answer_numbers:
        numbered = [
            candidate
            for candidate in candidates
            if any(number in candidate[1] for number in answer_numbers)
        ]
        if numbered:
            source_id, evidence = numbered[0]
            return f"{answer}\n\n根拠補足: {evidence} [S{source_id}]", True

    for source_id, evidence in candidates:
        if _bigram_similarity(plain_answer, evidence) < 0.30:
            return f"{answer}\n\n根拠補足: {evidence} [S{source_id}]", True
    return answer, False


def _bigram_similarity(left: str, right: str) -> float:
    """補完文が既存回答の言い換えだけにならないよう文字 bigram で比較する。"""
    def bigrams(value: str) -> set[str]:
        normalized = re.sub(r"\s+", "", value).lower()
        return {normalized[index : index + 2] for index in range(len(normalized) - 1)}

    left_values = bigrams(left)
    right_values = bigrams(right)
    union = left_values | right_values
    return len(left_values & right_values) / len(union) if union else 0.0
