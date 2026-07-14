"""ローカル検索結果を引用付きレスポンスに組み立てる RAG サービス。"""

import time

from app.models.chat import ChatResponse, Citation, RetrievedChunk, TokenUsage
from app.services.config import get_settings
from app.services.local_search_service import get_local_search_service

LOCAL_FALLBACK_ANSWER = (
    "ローカル知識ベースでは、ご質問に十分関連する情報が見つかりませんでした。"
    "質問の表現を変えるか、担当部署に確認してください。"
)


class LocalRagService:
    """生成モデルを使わず、実際のローカル検索結果を原文付きで返す。"""

    def answer(
        self,
        question: str,
        *,
        memory_context: str = "",
        access_groups: set[str] | None = None,
    ) -> ChatResponse:
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
                rag_mode="local",
                fallback_used=True,
            )

        context_chunks = results[:settings.max_chunks]
        top_chunk = context_chunks[0]
        answer = (
            "ローカル知識ベースから関連する記載を取得しました。"
            "現在は回答生成モデルを使用していないため、最上位の検索結果を原文で表示します。\n\n"
            f"【{top_chunk['title']} / {top_chunk['section']}】\n"
            f"{top_chunk['content']}"
        )

        return ChatResponse(
            answer=answer,
            citations=_build_citations(context_chunks),
            retrieved_chunks=[
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    title=f"{chunk['title']} / {chunk['section']}",
                    score=round(chunk["score"], 4),
                    content=chunk["content"][:300],
                )
                for chunk in results
            ],
            latency_ms=_elapsed_ms(started_at),
            rewritten_query=question,
            token_usage=TokenUsage(),
            rag_mode="local",
        )


def _build_citations(chunks: list[dict]) -> list[Citation]:
    citations: list[Citation] = []
    seen_sources: set[str] = set()
    for chunk in chunks:
        if chunk["source"] in seen_sources:
            continue
        seen_sources.add(chunk["source"])
        citations.append(
            Citation(
                title=f"{chunk['source']} / {chunk['section']}",
                chunk_id=chunk["chunk_id"],
                content=chunk["content"][:500],
            )
        )
    return citations


def _build_retrieved_chunks(chunks: list[dict]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=chunk["chunk_id"],
            title=f"{chunk['title']} / {chunk['section']}",
            score=round(chunk["score"], 4),
            content=chunk["content"][:300],
        )
        for chunk in chunks
    ]


def _build_extractive_answer(top_chunk: dict, *, generation_failed: bool = False) -> str:
    if generation_failed:
        prefix = (
            "ローカル生成モデルを利用できないため、安全のため検索結果の原文に切り替えました。"
        )
    else:
        prefix = "ローカル知識ベースから関連する記載を取得しました。"
    return (
        f"{prefix}\n\n"
        f"【{top_chunk['title']} / {top_chunk['section']}】\n"
        f"{top_chunk['content']}"
    )


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)
