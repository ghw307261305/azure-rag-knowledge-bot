"""
RAG オーケストレーションサービス
検索 → コンテキスト構築 → 回答生成 の一連の流れを担当する

設計上の判断:
- classic RAG を採用（agentic retrieval より制御性・速度を優先）
- query rewrite でハイブリッド検索の精度を向上
- スコア閾値でフォールバックを制御（hallucination 抑制）
- citation 重複排除はソースファイル単位で実施
"""
import logging
import time

from app.models.chat import ChatResponse, Citation, RetrievedChunk, TokenUsage
from app.services.config import get_settings
from app.services.openai_service import generate_answer, get_embedding, rewrite_query
from app.services.search_service import hybrid_search

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = "現在の資料では、ご質問に対する十分な情報が見つかりませんでした。関連部署にお問い合わせください。"
MIN_SCORE_THRESHOLD = 0.01


def answer(question: str) -> ChatResponse:
    """
    ユーザーの質問に対してRAGで回答する。

    Flow:
    1. クエリ書き換え（検索精度向上）
    2. 書き換えクエリをベクトル化
    3. Azure AI Search でハイブリッド検索（keyword + vector + RRF）
    4. スコア閾値チェック → 低ければフォールバック
    5. コンテキスト構築
    6. Azure OpenAI で回答生成
    7. レスポンス組み立て（citations 重複排除・token 追跡）
    """
    start = time.perf_counter()
    s = get_settings()

    # 1. クエリ書き換え
    rewritten = rewrite_query(question)

    # 2. 書き換えクエリをベクトル化
    query_vector = get_embedding(rewritten)

    # 3. ハイブリッド検索
    raw_chunks = hybrid_search(
        query=rewritten,
        query_vector=query_vector,
        top_k=s.top_k,
    )
    top_score = raw_chunks[0]["score"] if raw_chunks else 0
    logger.info(f"検索結果: {len(raw_chunks)}件 (top score: {top_score:.3f})")

    # 4. スコア閾値未満はフォールバック
    if not raw_chunks or top_score < MIN_SCORE_THRESHOLD:
        logger.info("スコア閾値未満のためフォールバック回答を返す")
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ChatResponse(
            answer=FALLBACK_ANSWER,
            citations=[],
            retrieved_chunks=[],
            latency_ms=latency_ms,
            rewritten_query=rewritten,
            token_usage=TokenUsage(),
        )

    # 5. コンテキスト構築（上位 max_chunks 件）
    chunks = raw_chunks[:s.max_chunks]
    context = _build_context(chunks)

    # 6. 回答生成
    answer_text, usage = generate_answer(question=question, context=context)
    logger.info(
        f"回答生成完了 | tokens: {usage['total_tokens']} "
        f"(prompt: {usage['prompt_tokens']}, completion: {usage['completion_tokens']})"
    )

    # 7. レスポンス組み立て
    latency_ms = int((time.perf_counter() - start) * 1000)
    return ChatResponse(
        answer=answer_text,
        citations=_build_citations(chunks),
        retrieved_chunks=_build_retrieved_chunks(raw_chunks),
        latency_ms=latency_ms,
        rewritten_query=rewritten,
        token_usage=TokenUsage(**usage),
    )


def _build_context(chunks: list[dict]) -> str:
    """検索結果チャンクをプロンプト用コンテキスト文字列に変換する"""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[資料{i}] {chunk['title']} / {chunk['section']}\n{chunk['content']}"
        )
    return "\n\n---\n\n".join(parts)


def _build_citations(chunks: list[dict]) -> list[Citation]:
    """
    重複ソース（同一ファイル）を除いた引用リストを作成する。
    同じドキュメントから複数チャンクが取れた場合も1件にまとめる。
    """
    seen: set[str] = set()
    citations: list[Citation] = []
    for chunk in chunks:
        key = chunk["source"]
        if key not in seen:
            seen.add(key)
            citations.append(Citation(
                title=chunk["title"],
                chunk_id=chunk["chunk_id"],
                content=chunk["content"][:300],
            ))
    return citations


def _build_retrieved_chunks(chunks: list[dict]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=c["chunk_id"],
            title=c["title"],
            score=round(c["score"], 4),
            content=c["content"][:200],
        )
        for c in chunks
    ]
