"""
Azure AI Search サービス
インデックス作成・ドキュメント登録・ハイブリッド検索を担当する
"""
import logging
from typing import List

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from app.services.config import get_settings

logger = logging.getLogger(__name__)


def _get_index_client() -> SearchIndexClient:
    s = get_settings()
    return SearchIndexClient(
        endpoint=s.azure_search_endpoint,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )


def _get_search_client() -> SearchClient:
    s = get_settings()
    return SearchClient(
        endpoint=s.azure_search_endpoint,
        index_name=s.azure_search_index_name,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )


def create_index() -> None:
    """インデックスが存在しない場合のみ作成する"""
    s = get_settings()
    client = _get_index_client()

    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="section", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-algo")],
    )

    index = SearchIndex(
        name=s.azure_search_index_name,
        fields=fields,
        vector_search=vector_search,
    )

    client.create_or_update_index(index)
    logger.info(f"Index '{s.azure_search_index_name}' created/updated.")


def delete_index() -> None:
    """インデックスを削除する（再構築時に使用）"""
    s = get_settings()
    client = _get_index_client()
    client.delete_index(s.azure_search_index_name)
    logger.info(f"Index '{s.azure_search_index_name}' deleted.")


def upload_documents(documents: List[dict]) -> None:
    """ドキュメントをバッチでアップロードする"""
    client = _get_search_client()
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        result = client.upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        failed = len(batch) - succeeded
        logger.info(f"Batch {i // batch_size + 1}: {succeeded} succeeded, {failed} failed")


def hybrid_search(query: str, query_vector: List[float], top_k: int) -> List[dict]:
    """
    ハイブリッド検索（キーワード + ベクトル）を実行する
    Azure AI Search の RRF で結果をマージして返す
    """
    client = _get_search_client()
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )

    results = client.search(
        search_text=query,
        vector_queries=[vector_query],
        select=["chunk_id", "title", "section", "source", "content"],
        top=top_k,
    )

    return [
        {
            "chunk_id": r["chunk_id"],
            "title": r["title"],
            "section": r.get("section", ""),
            "source": r["source"],
            "content": r["content"],
            "score": r["@search.score"],
        }
        for r in results
    ]
