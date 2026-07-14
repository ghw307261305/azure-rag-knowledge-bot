from functools import lru_cache
from typing import Protocol

from app.models.chat import ChatResponse
from app.services import rag_service as azure_rag_service
from app.services.config import get_settings
from app.services.local_rag_service import LocalRagService
from app.services.local_llm_rag_service import LocalLlmRagService
from app.services.mock_rag_service import MockRagService


class RagService(Protocol):
    def answer(self, question: str, *, memory_context: str = "") -> ChatResponse: ...


class AzureRagService:
    """Adapter for the existing Azure-backed RAG orchestration module."""

    def answer(self, question: str, *, memory_context: str = "") -> ChatResponse:
        return azure_rag_service.answer(question)


@lru_cache
def get_rag_service() -> RagService:
    mode = get_settings().rag_mode
    if mode == "mock":
        return MockRagService()
    if mode == "local":
        return LocalRagService()
    if mode == "local_llm":
        return LocalLlmRagService()
    return AzureRagService()
