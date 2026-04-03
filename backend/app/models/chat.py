from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str = Field(..., description="引用元ドキュメント名")
    chunk_id: str = Field(..., description="チャンク識別子")
    content: str = Field(..., description="引用本文")


class RetrievedChunk(BaseModel):
    chunk_id: str = Field(..., description="検索結果チャンク識別子")
    title: str = Field(..., description="検索結果のタイトル")
    score: float = Field(..., description="検索スコア")
    content: str = Field(..., description="検索結果本文")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, description="ユーザーからの質問")


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(0, description="プロンプトトークン数")
    completion_tokens: int = Field(0, description="補完トークン数")
    total_tokens: int = Field(0, description="合計トークン数")


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    latency_ms: int
    rewritten_query: str = Field("", description="検索用に書き換えたクエリ")
    token_usage: TokenUsage = Field(default_factory=TokenUsage)

