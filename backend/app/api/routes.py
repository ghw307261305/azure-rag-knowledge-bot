import logging
import time

from fastapi import APIRouter, HTTPException, Query

from app.models.chat import ChatRequest, ChatResponse
from app.services import rag_service
from app.services.openai_service import get_embedding
from app.services.search_service import create_index, hybrid_search

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": time.time()}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """RAGによる質問回答エンドポイント"""
    # 基本的なprompt injection防護
    if _is_suspicious(request.question):
        raise HTTPException(status_code=400, detail="不正なリクエストが検出されました")
    try:
        return rag_service.answer(request.question)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="回答生成中にエラーが発生しました")


@router.get("/search/debug")
def search_debug(q: str = Query(..., description="検索クエリ")) -> dict:
    """検索デバッグ用エンドポイント（検索スコアの確認に使用）"""
    try:
        query_vector = get_embedding(q)
        results = hybrid_search(query=q, query_vector=query_vector, top_k=5)
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
        logger.error(f"Search debug error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/rebuild")
def rebuild_index() -> dict:
    """インデックス再構築トリガー（開発・デバッグ用）"""
    try:
        create_index()
        return {"status": "ok", "message": "インデックスを再作成しました"}
    except Exception as e:
        logger.error(f"Index rebuild error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    ]
    return any(p in lower for p in patterns)
