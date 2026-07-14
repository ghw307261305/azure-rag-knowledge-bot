from app.models.chat import ChatResponse, Citation, RetrievedChunk, TokenUsage
from app.services.config import get_settings


class MockRagService:
    """Azure に接続せず、固定結果を返す開発・テスト用 RAG サービス。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def answer(self, question: str, *, memory_context: str = "") -> ChatResponse:
        retrieved_chunks = [
            RetrievedChunk(
                chunk_id="03-domestic-transfer-operations-004",
                title="国内振込の受付と実行 / FAQ",
                score=0.98,
                content=(
                    "RECEIVED の間は取消可能です。ACCEPTED 以降は単純取消ではなく、"
                    "組戻し手続として調査します。"
                ),
            ),
            RetrievedChunk(
                chunk_id="04-transfer-error-and-refund-002",
                title="誤振込・組戻し・返金対応 / 対応フロー",
                score=0.91,
                content=(
                    "実行済みの振込は組戻し案件として登録し、受取金融機関への連絡と"
                    "顧客同意を確認します。"
                ),
            ),
        ]

        citations = [
            Citation(
                title=chunk.title,
                chunk_id=chunk.chunk_id,
                content=chunk.content,
            )
            for chunk in retrieved_chunks[: self.settings.max_chunks]
        ]

        return ChatResponse(
            answer=(
                f"モック回答です。質問「{question}」に対して、"
                "固定の検索結果を根拠として返しています。"
            ),
            citations=citations,
            retrieved_chunks=retrieved_chunks[: self.settings.top_k],
            latency_ms=120,
            rewritten_query=question,
            token_usage=TokenUsage(),
        )
