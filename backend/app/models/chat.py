from typing import Literal

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
    client_id: str | None = Field(
        None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="ブラウザで生成した匿名クライアント識別子",
    )
    conversation_id: str | None = Field(
        None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="会話識別子",
    )
    use_memory: bool = Field(
        True,
        description="今回の質問で会話記憶の参照・保存を有効にするか",
    )


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(0, description="プロンプトトークン数")
    completion_tokens: int = Field(0, description="補完トークン数")
    total_tokens: int = Field(0, description="合計トークン数")


class MemoryUsage(BaseModel):
    enabled: bool = Field(False, description="会話記憶が有効か")
    context_items: int = Field(0, description="今回の回答で参照した記憶件数")
    stored_items: int = Field(0, description="今回新規または更新した記憶件数")
    masked_pii: list[str] = Field(default_factory=list, description="マスクした PII 種別")
    dropped_items: int = Field(0, description="品質または安全理由で保存しなかった件数")


class GenerationMetrics(BaseModel):
    context_chunks: int = 0
    context_characters: int = 0
    prompt_characters: int = 0
    model_load_ms: float = 0.0
    prompt_eval_ms: float = 0.0
    generation_ms: float = 0.0
    ollama_total_ms: float = 0.0
    prompt_tokens_per_second: float = 0.0
    generation_tokens_per_second: float = 0.0
    done_reason: str = ""
    fallback_reason: str = ""
    evidence_completion_used: bool = False


class ChatResponse(BaseModel):
    request_id: str = Field("", description="回答とフィードバックを関連付ける識別子")
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    latency_ms: int
    rewritten_query: str = Field("", description="検索用に書き換えたクエリ")
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    rag_mode: str = Field("", description="回答に使用した RAG 実行モード")
    model: str = Field("", description="回答生成に使用したモデル")
    fallback_used: bool = Field(False, description="安全な代替回答を使用したか")
    sanitized_question: str = Field("", description="PII 清洗後の質問")
    memory_usage: MemoryUsage = Field(default_factory=MemoryUsage)
    generation_metrics: GenerationMetrics = Field(default_factory=GenerationMetrics)


class FeedbackRequest(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=128)
    client_id: str | None = Field(
        None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    conversation_id: str = Field(
        ..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    rating: Literal["helpful", "unhelpful"]
    reason: str = Field("", max_length=500)


class FeedbackResponse(BaseModel):
    status: str = "ok"
    stored: bool = True
