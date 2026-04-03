import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str
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


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
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
    )

