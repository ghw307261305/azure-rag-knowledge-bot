"""環境変数を型付き設定へ集約し、起動前にモード別の必須値を検証する。"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """アプリ全体で共有する不変の実行時設定。"""
    app_env: str
    rag_mode: str
    log_level: str
    auth_mode: str
    local_jwt_secret: str
    local_jwt_issuer: str
    local_jwt_audience: str
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_chat_deployment: str
    azure_openai_embedding_deployment: str
    azure_search_endpoint: str
    azure_search_api_key: str
    azure_search_index_name: str
    top_k: int
    max_chunks: int
    local_min_score: float
    azure_min_score: float
    knowledge_dir: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    ollama_context_length: int
    ollama_temperature: float
    ollama_max_tokens: int
    ollama_keep_alive: str
    ollama_context_chunks: int
    ollama_context_score_ratio: float
    ollama_max_chunk_chars: int
    ollama_num_threads: int
    ollama_num_batch: int
    memory_enabled: bool
    memory_db_path: str
    memory_preference_ttl_days: int
    memory_fact_ttl_days: int
    memory_max_items: int
    feedback_db_path: str
    json_logs: bool
    otel_enabled: bool
    otel_service_name: str
    otel_exporter_endpoint: str


def _get_rag_mode() -> str:
    mode = os.getenv("RAG_MODE", "mock").strip().lower()
    supported_modes = {"mock", "local", "local_llm", "azure"}
    if mode not in supported_modes:
        supported = ", ".join(sorted(supported_modes))
        raise ValueError(f"RAG_MODE must be one of: {supported}")
    return mode


def _get_auth_mode() -> str:
    mode = os.getenv("AUTH_MODE", "disabled").strip().lower()
    supported_modes = {"disabled", "local_jwt"}
    if mode not in supported_modes:
        supported = ", ".join(sorted(supported_modes))
        raise ValueError(f"AUTH_MODE must be one of: {supported}")
    return mode


def validate_settings(settings: Settings) -> None:
    """選択した機能で実際に必要な設定だけを検証し、早期に失敗させる。"""
    """Fail fast when the selected runtime mode cannot be started safely."""
    if settings.rag_mode in {"local", "local_llm"}:
        knowledge_path = Path(settings.knowledge_dir)
        if not knowledge_path.is_absolute():
            knowledge_path = PROJECT_ROOT / knowledge_path
        if not knowledge_path.is_dir():
            raise ValueError(f"KNOWLEDGE_DIR does not exist: {knowledge_path}")
        if not any(knowledge_path.glob("*.md")):
            raise ValueError(f"KNOWLEDGE_DIR contains no Markdown files: {knowledge_path}")

    if settings.rag_mode == "azure":
        required = {
            "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
            "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
            "AZURE_OPENAI_CHAT_DEPLOYMENT": settings.azure_openai_chat_deployment,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": settings.azure_openai_embedding_deployment,
            "AZURE_SEARCH_ENDPOINT": settings.azure_search_endpoint,
            "AZURE_SEARCH_API_KEY": settings.azure_search_api_key,
            "AZURE_SEARCH_INDEX_NAME": settings.azure_search_index_name,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "Missing required settings for RAG_MODE=azure: " + ", ".join(missing)
            )

    if settings.auth_mode == "local_jwt" and len(settings.local_jwt_secret) < 32:
        raise ValueError("LOCAL_JWT_SECRET must contain at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    """環境変数の読み取り結果をキャッシュし、各サービスへ同じ設定を返す。"""
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        rag_mode=_get_rag_mode(),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        auth_mode=_get_auth_mode(),
        local_jwt_secret=os.getenv("LOCAL_JWT_SECRET", ""),
        local_jwt_issuer=os.getenv("LOCAL_JWT_ISSUER", "azure-rag-local"),
        local_jwt_audience=os.getenv("LOCAL_JWT_AUDIENCE", "azure-rag-api"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_openai_chat_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", ""),
        azure_openai_embedding_deployment=os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""
        ),
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
        azure_search_api_key=os.getenv("AZURE_SEARCH_API_KEY", ""),
        azure_search_index_name=os.getenv("AZURE_SEARCH_INDEX_NAME", "knowledge-index"),
        top_k=int(os.getenv("TOP_K", "5")),
        max_chunks=int(os.getenv("MAX_CHUNKS", "5")),
        local_min_score=float(os.getenv("LOCAL_MIN_SCORE", "0.06")),
        azure_min_score=float(os.getenv("AZURE_MIN_SCORE", "0.01")),
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "docs/knowledge-finance"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma3:4b-it-qat"),
        ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
        ollama_context_length=int(os.getenv("OLLAMA_CONTEXT_LENGTH", "2048")),
        ollama_temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0")),
        ollama_max_tokens=int(os.getenv("OLLAMA_MAX_TOKENS", "160")),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        ollama_context_chunks=int(os.getenv("OLLAMA_CONTEXT_CHUNKS", "2")),
        ollama_context_score_ratio=float(
            os.getenv("OLLAMA_CONTEXT_SCORE_RATIO", "0.90")
        ),
        ollama_max_chunk_chars=int(os.getenv("OLLAMA_MAX_CHUNK_CHARS", "1000")),
        ollama_num_threads=int(os.getenv("OLLAMA_NUM_THREADS", "4")),
        ollama_num_batch=int(os.getenv("OLLAMA_NUM_BATCH", "256")),
        memory_enabled=os.getenv("MEMORY_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        memory_db_path=os.getenv(
            "MEMORY_DB_PATH", "output/memory/conversation-memory.sqlite3"
        ),
        memory_preference_ttl_days=int(
            os.getenv("MEMORY_PREFERENCE_TTL_DAYS", "90")
        ),
        memory_fact_ttl_days=int(os.getenv("MEMORY_FACT_TTL_DAYS", "30")),
        memory_max_items=int(os.getenv("MEMORY_MAX_ITEMS", "12")),
        feedback_db_path=os.getenv(
            "FEEDBACK_DB_PATH", "output/feedback/feedback.sqlite3"
        ),
        json_logs=os.getenv("JSON_LOGS", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        otel_enabled=os.getenv("OTEL_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        otel_service_name=os.getenv(
            "OTEL_SERVICE_NAME", "azure-rag-knowledge-bot-backend"
        ),
        otel_exporter_endpoint=os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"
        ),
    )
