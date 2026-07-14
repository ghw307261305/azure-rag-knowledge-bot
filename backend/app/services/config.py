import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_env: str
    rag_mode: str
    log_level: str
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


def _get_rag_mode() -> str:
    mode = os.getenv("RAG_MODE", "mock").strip().lower()
    supported_modes = {"mock", "local", "local_llm", "azure"}
    if mode not in supported_modes:
        supported = ", ".join(sorted(supported_modes))
        raise ValueError(f"RAG_MODE must be one of: {supported}")
    return mode


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        rag_mode=_get_rag_mode(),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
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
    )
