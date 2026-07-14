"""PII-sanitized local feedback persistence for the PoC quality loop."""

import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.services.config import PROJECT_ROOT, get_settings
from app.services.conversation_memory_service import sanitize_text


class FeedbackService:
    """回答評価を PII 安全化後に保存し、同一回答への再評価は更新する。"""
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    client_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    rating TEXT NOT NULL CHECK(rating IN ('helpful', 'unhelpful')),
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(client_id, request_id)
                )
                """
            )
            connection.commit()

    def store(
        self,
        *,
        client_id: str,
        request_id: str,
        conversation_id: str,
        rating: str,
        reason: str,
    ) -> None:
        """自由記述理由を安全化し、client/request の組み合わせで upsert する。"""
        sanitized_reason = sanitize_text(reason).text[:500]
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (
                    client_id, request_id, conversation_id, rating, reason,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id, request_id) DO UPDATE SET
                    rating = excluded.rating,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (
                    client_id,
                    request_id,
                    conversation_id,
                    rating,
                    sanitized_reason,
                    now,
                    now,
                ),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)


@lru_cache
def get_feedback_service() -> FeedbackService:
    settings = get_settings()
    configured = Path(settings.feedback_db_path)
    db_path = configured if configured.is_absolute() else PROJECT_ROOT / configured
    return FeedbackService(db_path)
