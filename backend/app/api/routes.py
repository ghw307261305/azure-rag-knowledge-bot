"""HTTP 入出力をサービス層へ橋渡しする API ルーター。"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.models.chat import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    MemoryUsage,
)
from app.models.memory import (
    MemoryCleanupResponse,
    MemoryDeleteResponse,
    MemoryListResponse,
)
from app.services.config import get_settings
from app.services.auth_service import Principal, get_current_principal, require_roles
from app.services.conversation_memory_service import get_conversation_memory_service
from app.services.feedback_service import get_feedback_service
from app.services.logging_service import get_request_id
from app.services.local_search_service import get_local_search_service
from app.services.openai_service import get_embedding
from app.services.observability_service import get_observability_service
from app.services.rag_service_factory import get_rag_service
from app.services.search_service import create_index, hybrid_search

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    """現在の RAG モードと、ローカル実行時の準備状況を返す。"""
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
def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
) -> ChatResponse:
    """入力を安全化し、記憶の準備後に選択中の RAG サービスへ回答を委譲する。"""
    # 基本的なprompt injection防護
    if _is_suspicious(request.question):
        raise HTTPException(status_code=400, detail="不正なリクエストが検出されました")
    try:
        memory_service = get_conversation_memory_service()
        effective_client_id = _resolve_memory_client_id(
            request.client_id, principal, required=False
        )
        # PII マスクと記憶候補の抽出は、検索・生成より前に一度だけ行う。
        preparation = memory_service.prepare(
            client_id=effective_client_id,
            conversation_id=request.conversation_id,
            question=request.question,
            enabled_for_request=request.use_memory,
        )
        if not preparation.sanitized_question:
            raise HTTPException(status_code=400, detail="有効な質問がありません")
        # ファクトリが mock/local/local_llm/azure の差を吸収する。
        response = get_rag_service().answer(
            preparation.sanitized_question,
            memory_context=preparation.memory_context,
            access_groups=principal.access_groups,
        )
        response.sanitized_question = preparation.sanitized_question
        response.request_id = get_request_id()
        response.memory_usage = MemoryUsage(
            enabled=bool(
                get_settings().memory_enabled
                and request.use_memory
                and effective_client_id
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


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(
    request: FeedbackRequest,
    principal: Principal = Depends(get_current_principal),
) -> FeedbackResponse:
    """回答単位の評価を、認証主体または匿名クライアントに紐付けて保存する。"""
    client_id = _resolve_memory_client_id(request.client_id, principal)
    get_feedback_service().store(
        client_id=client_id,
        request_id=request.request_id,
        conversation_id=request.conversation_id,
        rating=request.rating,
        reason=request.reason,
    )
    return FeedbackResponse()


@router.get("/memory", response_model=MemoryListResponse)
def list_memory(
    client_id: str | None = Query(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    principal: Principal = Depends(get_current_principal),
) -> MemoryListResponse:
    """呼び出し主体が所有する、有効期限内の会話記憶だけを返す。"""
    client_id = _resolve_memory_client_id(client_id, principal)
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
    client_id: str | None = Query(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    conversation_id: str | None = Query(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    principal: Principal = Depends(get_current_principal),
) -> MemoryDeleteResponse:
    """クライアント全体、または指定した会話に属する記憶を削除する。"""
    client_id = _resolve_memory_client_id(client_id, principal)
    deleted = get_conversation_memory_service().delete_items(
        client_id, conversation_id
    )
    return MemoryDeleteResponse(deleted=deleted)


@router.delete("/memory/items/{item_id}", response_model=MemoryDeleteResponse)
def delete_memory_item(
    item_id: str,
    client_id: str | None = Query(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    ),
    principal: Principal = Depends(get_current_principal),
) -> MemoryDeleteResponse:
    resolved_client_id = _resolve_memory_client_id(client_id, principal)
    deleted = get_conversation_memory_service().delete_item(
        resolved_client_id, item_id
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="指定した会話記憶が見つかりません")
    return MemoryDeleteResponse(deleted=deleted)


@router.post("/memory/cleanup", response_model=MemoryCleanupResponse)
def cleanup_memory(
    _principal: Principal = Depends(require_roles("admin")),
) -> MemoryCleanupResponse:
    """管理者操作として TTL 超過済みの記憶を物理削除する。"""
    deleted = get_conversation_memory_service().cleanup_expired()
    return MemoryCleanupResponse(expired_deleted=deleted)


@router.get("/observability")
def observability(
    _principal: Principal = Depends(require_roles("operator", "admin")),
) -> dict:
    """運用者向けに、プロセス内の品質・性能指標と資源情報を返す。"""
    service = get_observability_service()
    return {
        "metrics": service.summary(),
        "resources": service.resource_snapshot(),
    }


@router.delete("/observability")
def reset_observability(
    _principal: Principal = Depends(require_roles("admin")),
) -> dict:
    cleared = get_observability_service().reset()
    return {"status": "ok", "cleared_samples": cleared}


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    """Low-cardinality local metrics endpoint; protect at the network edge in production."""
    return get_observability_service().prometheus_text()


@router.get("/search/debug")
def search_debug(
    q: str = Query(..., description="検索クエリ"),
    principal: Principal = Depends(require_roles("operator", "admin")),
) -> dict:
    """現在の実行モードで検索だけを行い、ランキングとスコアを確認する。"""
    try:
        mode = get_settings().rag_mode
        if mode in {"local", "local_llm"}:
            results = get_local_search_service().search(
                q,
                top_k=5,
                allowed_groups=principal.access_groups,
            )
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
def rebuild_index(
    _principal: Principal = Depends(require_roles("admin")),
) -> dict:
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


def _resolve_memory_client_id(
    requested_client_id: str | None,
    principal: Principal,
    *,
    required: bool = True,
) -> str | None:
    """認証済み主体の ID を優先し、他ユーザーの記憶指定を防ぐ。"""
    if principal.authenticated:
        return principal.subject
    if requested_client_id:
        return requested_client_id
    if required:
        raise HTTPException(status_code=400, detail="client_id が必要です")
    return None
