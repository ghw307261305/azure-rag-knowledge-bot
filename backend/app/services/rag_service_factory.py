"""設定された実行モードを、共通の RAG サービス契約へ変換する。"""

from functools import lru_cache
from typing import Protocol

from app.models.chat import ChatResponse
from app.services import rag_service as azure_rag_service
from app.services.config import get_settings
from app.services.local_rag_service import LocalRagService
from app.services.local_llm_rag_service import LocalLlmRagService
from app.services.mock_rag_service import MockRagService


class RagService(Protocol):
    """API 層が実装方式を意識せず回答を取得するための最小契約。"""
    def answer(
        self,
        question: str,
        *,
        memory_context: str = "",
        access_groups: set[str] | None = None,
    ) -> ChatResponse: ...


class AzureRagService:
    """既存の Azure RAG 関数を共通サービス契約へ合わせるアダプター。"""

    def answer(
        self,
        question: str,
        *,
        memory_context: str = "",
        access_groups: set[str] | None = None,
    ) -> ChatResponse:
        return azure_rag_service.answer(question, access_groups=access_groups)


@lru_cache
def get_rag_service() -> RagService:
    """RAG_MODE に対応する実装をプロセス内で一度だけ生成する。"""
    mode = get_settings().rag_mode
    if mode == "mock":
        return MockRagService()
    if mode == "local":
        return LocalRagService()
    if mode == "local_llm":
        return LocalLlmRagService()
    return AzureRagService()
