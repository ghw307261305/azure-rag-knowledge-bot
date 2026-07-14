"""会話記憶の参照・削除・クリーンアップ API で共有するスキーマ。"""

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """PII 除去後に保存を許可された preference または明示的 fact。"""
    id: str
    conversation_id: str
    kind: str
    key: str
    value: str
    confidence: float
    source: str
    created_at: str
    updated_at: str
    expires_at: str


class MemoryListResponse(BaseModel):
    enabled: bool
    client_id: str
    total: int
    items: list[MemoryItem]


class MemoryDeleteResponse(BaseModel):
    status: str = "ok"
    deleted: int = Field(0, ge=0)


class MemoryCleanupResponse(BaseModel):
    status: str = "ok"
    expired_deleted: int = Field(0, ge=0)
