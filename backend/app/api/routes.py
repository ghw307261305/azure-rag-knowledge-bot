import logging
import time

from fastapi import APIRouter, HTTPException, Query

from app.models.chat import ChatRequest, ChatResponse, MemoryUsage
from app.models.memory import (
    MemoryCleanupResponse,
    MemoryDeleteResponse,
    MemoryListResponse,
)
from app.services.config import get_settings
from app.services.conversation_memory_service import get_conversation_memory_service
from app.services.local_search_service import get_local_search_service
from app.services.openai_service import get_embedding
from app.services.observability_service import get_observability_service
from app.services.rag_service_factory import get_rag_service
from app.services.search_service import create_index, hybrid_search

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    result = {
        "status": "ok",
        "timestamp": time.time(),
        "rag_mode": settings.rag_mode,
    }
    if settings.rag_mode in {"local", "local_llm"}:
        local_search = get_local_search_service()
        result["knowledge_dir"] = str(local_search.knowledge_dir)
        result["chunk_count"] = local_search.chunk_count
    if settings.rag_mode == "local_llm":
        result["generation_model"] = settings.ollama_model
    result["memory_enabled"] = settings.memory_enabled
    return result


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """RAGによる質問回答エンドポイント"""
    # 基本的なprompt injection防護
    if _is_suspicious(request.question):
        raise HTTPException(status_code=400, detail="不正なリクエストが検出されました")
    try:
        memory_service = get_conversation_memory_service()
        preparation = memory_service.prepare(
            client_id=request.client_id,
            conversation_id=request.conversation_id,
            question=request.question,
        )
        if not preparation.sanitized_question:
            raise HTTPException(status_code=400, detail="有効な質問がありません")
        response = get_rag_service().answer(
            preparation.sanitized_question,
            memory_context=preparation.memory_context,
        )
        response.sanitized_question = preparation.sanitized_question
        response.memory_usage = MemoryUsage(
            enabled=bool(
                get_settings().memory_enabled
                and request.client_id
                and request.conversation_id
            ),
            context_items=preparation.context_items,
            stored_items=preparation.stored_items,
            masked_pii=list(preparation.masked_pii),
            dropped_items=preparation.dropped_items,
        )
        get_observability_service().record(response)
        return response
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="回答生成中にエラーが発生しました")


@router.get("/memory", response_model=MemoryListResponse)
def list_memory(
    client_id: str = Query(
        ..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
) -> MemoryListResponse:
    service = get_conversation_memory_service()
    items = service.list_items(client_id)
    return MemoryListResponse(
        enabled=service.enabled,
        client_id=client_id,
        total=len(items),
        items=items,
    )


@router.delete("/memory", response_model=MemoryDeleteResponse)
def delete_memory(
    client_id: str = Query(
        ..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    conversation_id: str | None = Query(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
) -> MemoryDeleteResponse:
    deleted = get_conversation_memory_service().delete_items(
        client_id, conversation_id
    )
    return MemoryDeleteResponse(deleted=deleted)


@router.post("/memory/cleanup", response_model=MemoryCleanupResponse)
def cleanup_memory() -> MemoryCleanupResponse:
    deleted = get_conversation_memory_service().cleanup_expired()
    return MemoryCleanupResponse(expired_deleted=deleted)


@router.get("/observability")
def observability() -> dict:
    service = get_observability_service()
    return {
        "metrics": service.summary(),
        "resources": service.resource_snapshot(),
    }


@router.delete("/observability")
def reset_observability() -> dict:
    cleared = get_observability_service().reset()
    return {"status": "ok", "cleared_samples": cleared}


@router.get("/search/debug")
def search_debug(q: str = Query(..., description="検索クエリ")) -> dict:
    """検索デバッグ用エンドポイント（検索スコアの確認に使用）"""
    try:
        mode = get_settings().rag_mode
        if mode in {"local", "local_llm"}:
            results = get_local_search_service().search(q, top_k=5)
        elif mode == "azure":
            query_vector = get_embedding(q)
            results = hybrid_search(query=q, query_vector=query_vector, top_k=5)
        else:
            _raise_mode_unavailable("search/debug")
        return {
            "query": q,
            "total": len(results),
            "results": [
                {
                    "rank": i + 1,
                    "chunk_id": r["chunk_id"],
                    "title": r["title"],
                    "section": r["section"],
                    "score": round(r["score"], 4),
                    "content_preview": r["content"][:150],
                }
                for i, r in enumerate(results)
            ],
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"Search debug error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/rebuild")
def rebuild_index() -> dict:
    """インデックス再構築トリガー（開発・デバッグ用）"""
    try:
        mode = get_settings().rag_mode
        if mode in {"local", "local_llm"}:
            chunk_count = get_local_search_service().rebuild()
            return {
                "status": "ok",
                "message": "ローカルインデックスを再作成しました",
                "chunk_count": chunk_count,
                "knowledge_dir": str(get_local_search_service().knowledge_dir),
            }
        if mode == "azure":
            create_index()
            return {"status": "ok", "message": "インデックスを再作成しました"}
        _raise_mode_unavailable("index/rebuild")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"Index rebuild error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _raise_mode_unavailable(endpoint: str) -> None:
    raise HTTPException(
        status_code=503,
        detail=(
            f"/{endpoint} は RAG_MODE=local、local_llm または azure の場合のみ利用できます"
        ),
    )


def _is_suspicious(text: str) -> bool:
    """基本的なprompt injection検出"""
    lower = text.lower()
    patterns = [
        "ignore previous",
        "ignore all",
        "disregard",
        "forget everything",
        "<script",
        "system prompt",
        "忽略之前",
        "忽略以上",
        "无视之前",
        "系統提示詞",
        "系统提示词",
        "以前の指示を無視",
        "指示を無視",
        "システムプロンプト",
    ]
    return any(p in lower for p in patterns)
