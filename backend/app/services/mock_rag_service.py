from app.models.chat import ChatResponse, Citation, RetrievedChunk
from app.services.config import get_settings


class MockRagService:
    """Day 1 向けのモック RAG サービス。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def answer(self, question: str) -> ChatResponse:
        retrieved_chunks = [
            RetrievedChunk(
                chunk_id="job-posting-rule-001",
                title="job-posting-rule.md",
                score=0.98,
                content=(
                    "学校ユーザーが公開求人を登録するには、審査済みアカウントであり、"
                    "応募締切日が現在日付より後である必要があります。"
                ),
            ),
            RetrievedChunk(
                chunk_id="application-flow-001",
                title="application-flow.md",
                score=0.91,
                content=(
                    "応募済みの求人は削除できず、公開停止に変更して運用担当者へ連絡します。"
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
                "Day 1 では固定の検索結果を根拠として返しています。"
            ),
            citations=citations,
            retrieved_chunks=retrieved_chunks[: self.settings.top_k],
            latency_ms=120,
        )

