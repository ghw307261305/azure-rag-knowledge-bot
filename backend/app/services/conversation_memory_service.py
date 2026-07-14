"""Governed local conversation memory with sanitization, TTL and user control."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from app.models.memory import MemoryItem
from app.services.config import PROJECT_ROOT, get_settings

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+81[- ]?|0)\d{1,4}[- ]?\d{1,4}[- ]?\d{3,4}(?!\d)")
POSTAL_PATTERN = re.compile(r"(?<!\d)〒?\d{3}-?\d{4}(?!\d)")
EXPLICIT_ACCOUNT_PATTERN = re.compile(
    r"(?P<label>口座番号|顧客番号|account(?:\s+number)?|customer\s+id)"
    r"\s*[:：]?\s*[A-Za-z0-9-]{4,}",
    re.I,
)
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{10,19}(?!\d)")
HTML_TAG_PATTERN = re.compile(r"<[^>]{1,200}>")
CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
REPEATED_PATTERN = re.compile(r"(.)\1{8,}")
SOURCE_MARKER_PATTERN = re.compile(r"\[S\d+\]")
MAX_INPUT_CHARS = 2000
MAX_SUMMARY_TOPIC_CHARS = 300

FOLLOW_UP_PATTERNS = (
    r"(?:刚才|剛才|上述|上面|前面|那个|那個|这个|這個|该规定|該規定|那条|那條|这种情况|這種情況)",
    r"(?:それ|その|あれ|先ほど|さっき|上記|前述|この規定|その規定|その場合)",
    r"\b(?:that|those|it|previous|earlier|above|same)\b",
    r"\bwhat\s+about\b",
)
SHORT_FOLLOW_UP_PATTERN = re.compile(
    r"(?:呢|呢[?？]|は[?？]|はどう|どうですか|では[?？]?|じゃあ|what about)[。.!！?？]*$",
    re.I,
)

POISON_PATTERNS = (
    "ignore previous",
    "ignore all",
    "system prompt",
    "忽略之前",
    "忽略以上",
    "系统提示词",
    "系統提示詞",
    "以前の指示を無視",
    "指示を無視",
    "システムプロンプト",
)


@dataclass(frozen=True)
class SanitizationResult:
    """安全化した本文と、マスク・除去した内容の監査情報。"""
    text: str
    masked_pii: tuple[str, ...]
    dirty_events: tuple[str, ...]


@dataclass(frozen=True)
class MemoryPreparation:
    """RAG 呼び出し前に必要な、安全化済み質問と許可済み記憶。"""
    sanitized_question: str
    effective_question: str
    memory_context: str
    context_items: int
    stored_items: int
    masked_pii: tuple[str, ...]
    dropped_items: int
    summary_used: bool
    follow_up_detected: bool


@dataclass(frozen=True)
class MemoryCandidate:
    """保存前の preference/fact 候補。信頼度と抽出元も保持する。"""
    kind: str
    key: str
    value: str
    confidence: float
    source: str


class ConversationMemoryService:
    """PII、TTL、所有者境界を強制する SQLite ベースの会話記憶。"""
    def __init__(
        self,
        db_path: Path,
        *,
        enabled: bool = True,
        preference_ttl_days: int = 90,
        fact_ttl_days: int = 30,
        summary_ttl_days: int = 7,
        summary_max_turns: int = 3,
        max_items: int = 12,
    ) -> None:
        self.db_path = db_path.resolve()
        self.enabled = enabled
        self.preference_ttl_days = preference_ttl_days
        self.fact_ttl_days = fact_ttl_days
        self.summary_ttl_days = max(1, summary_ttl_days)
        self.summary_max_turns = max(1, summary_max_turns)
        self.max_items = max_items
        if self.enabled:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def prepare(
        self,
        *,
        client_id: str | None,
        conversation_id: str | None,
        question: str,
        enabled_for_request: bool = True,
    ) -> MemoryPreparation:
        """質問を安全化し、保存候補の審査と既存記憶の読込を一括実行する。"""
        sanitized = sanitize_text(question)
        if (
            not self.enabled
            or not enabled_for_request
            or not client_id
            or not conversation_id
        ):
            return MemoryPreparation(
                sanitized_question=sanitized.text,
                effective_question=sanitized.text,
                memory_context="",
                context_items=0,
                stored_items=0,
                masked_pii=sanitized.masked_pii,
                dropped_items=len(sanitized.dirty_events),
                summary_used=False,
                follow_up_detected=False,
            )

        self.cleanup_expired()
        summary_topics = self._get_summary_topics(client_id, conversation_id)
        follow_up_detected = bool(
            summary_topics and is_contextual_follow_up(sanitized.text)
        )
        effective_question = (
            build_contextual_query(summary_topics, sanitized.text)
            if follow_up_detected
            else sanitized.text
        )
        candidates = extract_memory_candidates(sanitized.text)
        dropped_items = len(sanitized.dirty_events)
        # 指示上書きが疑われる入力は質問には使えても、長期記憶には保存しない。
        if _contains_memory_poisoning(sanitized.text):
            dropped_items += max(1, len(candidates))
            candidates = []
        if sanitized.masked_pii:
            # マスク記号を含む候補は、復元不能でも機微情報由来なので保存しない。
            safe_candidates = [
                candidate
                for candidate in candidates
                if not re.search(r"\[[A-Z_]+\]", candidate.value)
            ]
            dropped_items += len(candidates) - len(safe_candidates)
            candidates = safe_candidates

        for candidate in candidates:
            self._upsert(client_id, conversation_id, candidate)
        items = self._list_long_term_items(client_id)
        return MemoryPreparation(
            sanitized_question=sanitized.text,
            effective_question=effective_question,
            memory_context=build_memory_context(items),
            context_items=len(items) + int(follow_up_detected),
            stored_items=len(candidates),
            masked_pii=sanitized.masked_pii,
            dropped_items=dropped_items,
            summary_used=follow_up_detected,
            follow_up_detected=follow_up_detected,
        )

    def list_items(self, client_id: str) -> list[MemoryItem]:
        """長期記憶と短期会話摘要を、利用者が確認・削除できる形で返す。"""
        items = self._list_long_term_items(client_id)
        items.extend(self._list_summary_items(client_id))
        priority = {"preference": 0, "summary": 1, "fact": 2}
        items.sort(key=lambda item: item.updated_at, reverse=True)
        items.sort(
            key=lambda item: (
                priority.get(item.kind, 9),
                -item.confidence,
            )
        )
        return items[: self.max_items]

    def _list_long_term_items(self, client_id: str) -> list[MemoryItem]:
        """有効な preference / fact を信頼度順で返す。"""
        if not self.enabled:
            return []
        now = _utc_now().isoformat()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, kind, memory_key, value, confidence,
                       source, created_at, updated_at, expires_at
                FROM memory_items
                WHERE client_id = ? AND status = 'active' AND expires_at > ?
                ORDER BY CASE kind WHEN 'preference' THEN 0 ELSE 1 END,
                         confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (client_id, now, self.max_items),
            ).fetchall()
        return [
            MemoryItem(
                id=row["id"],
                conversation_id=row["conversation_id"],
                kind=row["kind"],
                key=row["memory_key"],
                value=row["value"],
                confidence=float(row["confidence"]),
                source=row["source"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                expires_at=row["expires_at"],
            )
            for row in rows
        ]

    def _list_summary_items(self, client_id: str) -> list[MemoryItem]:
        if not self.enabled:
            return []
        now = _utc_now().isoformat()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, topics_json, created_at, updated_at,
                       expires_at
                FROM conversation_summaries
                WHERE client_id = ? AND expires_at > ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (client_id, now, self.max_items),
            ).fetchall()
        items: list[MemoryItem] = []
        for row in rows:
            topics = _parse_topics(row["topics_json"])
            if not topics:
                continue
            items.append(
                MemoryItem(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    kind="summary",
                    key="recent_conversation_topics",
                    value=" → ".join(topics),
                    confidence=1.0,
                    source="controlled_summary",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                )
            )
        return items

    def remember_turn(
        self,
        *,
        client_id: str | None,
        conversation_id: str | None,
        question: str,
        follow_up_detected: bool,
        enabled_for_request: bool = True,
    ) -> bool:
        """成功した質問だけを短いトピック列へ圧縮し、原始会話全文は保存しない。"""
        if (
            not self.enabled
            or not enabled_for_request
            or not client_id
            or not conversation_id
        ):
            return False
        sanitized = sanitize_text(question)
        if (
            not sanitized.text
            or sanitized.masked_pii
            or re.search(r"\[[A-Z_]+\]", sanitized.text)
            or _contains_memory_poisoning(sanitized.text)
            or _is_memory_control_only(sanitized.text)
        ):
            return False

        topic = _compact_topic(sanitized.text)
        if not topic:
            return False
        topics = (
            self._get_summary_topics(client_id, conversation_id)
            if follow_up_detected
            else []
        )
        if not topics or topics[-1] != topic:
            topics.append(topic)
        topics = topics[-self.summary_max_turns :]
        self._upsert_summary(client_id, conversation_id, topics)
        return True

    def delete_items(self, client_id: str, conversation_id: str | None = None) -> int:
        if not self.enabled:
            return 0
        with self._connection() as connection:
            if conversation_id:
                memory_cursor = connection.execute(
                    "DELETE FROM memory_items WHERE client_id = ? AND conversation_id = ?",
                    (client_id, conversation_id),
                )
                summary_cursor = connection.execute(
                    "DELETE FROM conversation_summaries "
                    "WHERE client_id = ? AND conversation_id = ?",
                    (client_id, conversation_id),
                )
            else:
                memory_cursor = connection.execute(
                    "DELETE FROM memory_items WHERE client_id = ?", (client_id,)
                )
                summary_cursor = connection.execute(
                    "DELETE FROM conversation_summaries WHERE client_id = ?",
                    (client_id,),
                )
            connection.commit()
            return max(0, memory_cursor.rowcount) + max(0, summary_cursor.rowcount)

    def delete_item(self, client_id: str, item_id: str) -> int:
        if not self.enabled:
            return 0
        with self._connection() as connection:
            memory_cursor = connection.execute(
                "DELETE FROM memory_items WHERE client_id = ? AND id = ?",
                (client_id, item_id),
            )
            summary_cursor = connection.execute(
                "DELETE FROM conversation_summaries WHERE client_id = ? AND id = ?",
                (client_id, item_id),
            )
            connection.commit()
            return max(0, memory_cursor.rowcount) + max(0, summary_cursor.rowcount)

    def cleanup_expired(self) -> int:
        if not self.enabled:
            return 0
        with self._connection() as connection:
            memory_cursor = connection.execute(
                "DELETE FROM memory_items WHERE expires_at <= ?",
                (_utc_now().isoformat(),),
            )
            summary_cursor = connection.execute(
                "DELETE FROM conversation_summaries WHERE expires_at <= ?",
                (_utc_now().isoformat(),),
            )
            connection.commit()
            return max(0, memory_cursor.rowcount) + max(0, summary_cursor.rowcount)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('preference', 'fact')),
                    memory_key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE(client_id, kind, memory_key)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_active "
                "ON memory_items(client_id, status, expires_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    turn_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    UNIQUE(client_id, conversation_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_summary_active "
                "ON conversation_summaries(client_id, conversation_id, expires_at)"
            )
            connection.commit()

    def _upsert(
        self, client_id: str, conversation_id: str, candidate: MemoryCandidate
    ) -> None:
        """同じ意味キーを更新し、種別ごとの TTL を最終確認時点から延長する。"""
        now = _utc_now()
        ttl_days = (
            self.preference_ttl_days
            if candidate.kind == "preference"
            else self.fact_ttl_days
        )
        expires_at = now + timedelta(days=ttl_days)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO memory_items (
                    id, client_id, conversation_id, kind, memory_key, value,
                    confidence, source, created_at, updated_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(client_id, kind, memory_key) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    value = excluded.value,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at,
                    status = 'active'
                """,
                (
                    str(uuid.uuid4()),
                    client_id,
                    conversation_id,
                    candidate.kind,
                    candidate.key,
                    candidate.value,
                    candidate.confidence,
                    candidate.source,
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Transaction 完了後に OS のデータベースハンドルも確実に閉じる。"""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _get_summary_topics(
        self, client_id: str, conversation_id: str
    ) -> list[str]:
        if not self.enabled:
            return []
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT topics_json
                FROM conversation_summaries
                WHERE client_id = ? AND conversation_id = ? AND expires_at > ?
                """,
                (client_id, conversation_id, _utc_now().isoformat()),
            ).fetchone()
        return _parse_topics(row["topics_json"]) if row else []

    def _upsert_summary(
        self, client_id: str, conversation_id: str, topics: list[str]
    ) -> None:
        now = _utc_now()
        expires_at = now + timedelta(days=self.summary_ttl_days)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO conversation_summaries (
                    id, client_id, conversation_id, topics_json, turn_count,
                    created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id, conversation_id) DO UPDATE SET
                    topics_json = excluded.topics_json,
                    turn_count = excluded.turn_count,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    str(uuid.uuid4()),
                    client_id,
                    conversation_id,
                    json.dumps(topics, ensure_ascii=False),
                    len(topics),
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            connection.commit()


def sanitize_text(text: str) -> SanitizationResult:
    """制御文字や過剰入力を整形し、既知の PII を不可逆なラベルへ置換する。"""
    value = unicodedata.normalize("NFKC", text)
    value = ZERO_WIDTH_PATTERN.sub("", value)
    value = CONTROL_PATTERN.sub("", value)
    dirty_events: list[str] = []
    if HTML_TAG_PATTERN.search(value):
        value = HTML_TAG_PATTERN.sub(" ", value)
        dirty_events.append("html_removed")
    if REPEATED_PATTERN.search(value):
        value = REPEATED_PATTERN.sub(lambda match: match.group(1) * 3, value)
        dirty_events.append("repetition_collapsed")
    if len(value) > MAX_INPUT_CHARS:
        value = value[:MAX_INPUT_CHARS]
        dirty_events.append("truncated")

    masked: list[str] = []
    value = _mask(value, EMAIL_PATTERN, "[EMAIL]", "email", masked)
    value = _mask(value, PHONE_PATTERN, "[PHONE]", "phone", masked)
    value = _mask(value, POSTAL_PATTERN, "[POSTAL_CODE]", "postal_code", masked)

    def replace_account(match: re.Match[str]) -> str:
        if "account_number" not in masked:
            masked.append("account_number")
        return f"{match.group('label')}:[ACCOUNT_NUMBER]"

    value = EXPLICIT_ACCOUNT_PATTERN.sub(replace_account, value)
    value = _mask(value, LONG_NUMBER_PATTERN, "[LONG_NUMBER]", "long_number", masked)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return SanitizationResult(value, tuple(masked), tuple(dirty_events))


def extract_memory_candidates(text: str) -> list[MemoryCandidate]:
    """明示された言語・回答形式・remember 指示だけを保存候補として抽出する。"""
    candidates: list[MemoryCandidate] = []
    lower = text.lower()
    language_patterns = (
        (r"(?:请|請)?(?:以后|今后)?(?:用|使用)(中文|汉语|漢語)(?:回答)?", "中文"),
        (r"(?:请|請)?(?:以后|今后)?(?:用|使用)(日语|日文)(?:回答)?", "日本語"),
        (r"(?:请|請)?(?:以后|今后)?(?:用|使用)(英语|英文)(?:回答)?", "English"),
        (r"(日本語)で(?:回答|返答)", "日本語"),
        (r"(中国語)で(?:回答|返答)", "中文"),
        (r"(英語)で(?:回答|返答)", "English"),
        (r"reply in (chinese)", "中文"),
        (r"reply in (japanese)", "日本語"),
        (r"reply in (english)", "English"),
    )
    for pattern, value in language_patterns:
        if re.search(pattern, text, re.I):
            candidates.append(
                MemoryCandidate("preference", "response_language", value, 0.9, "explicit")
            )
            break

    if any(term in lower for term in ("简洁", "簡潔", "concise", "short answer")):
        candidates.append(
            MemoryCandidate("preference", "answer_style", "concise", 0.85, "explicit")
        )
    elif any(term in lower for term in ("详细", "詳細", "詳しく", "detailed")):
        candidates.append(
            MemoryCandidate("preference", "answer_style", "detailed", 0.85, "explicit")
        )

    explicit_patterns = (
        r"(?:请|請)?记住\s*[:：]\s*(.+)",
        r"覚えておいて\s*[:：]?\s*(.+)",
        r"remember that\s*[:：]?\s*(.+)",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        fact = SOURCE_MARKER_PATTERN.sub("", match.group(1)).strip(" 。.")[:200]
        if fact and not _contains_memory_poisoning(fact):
            digest = hashlib.sha256(_normalize_key(fact).encode("utf-8")).hexdigest()[:12]
            candidates.append(
                MemoryCandidate("fact", f"explicit_{digest}", fact, 0.9, "explicit")
            )
        break
    return _deduplicate_candidates(candidates)


def build_memory_context(items: list[MemoryItem]) -> str:
    """モデルが通常の会話と区別できる、閉じた記憶ブロックへ整形する。"""
    governed_items = [item for item in items if item.kind in {"preference", "fact"}]
    if not governed_items:
        return ""
    lines = ["<governed_memory>"]
    for item in governed_items:
        lines.append(
            f"[{item.kind}] {item.key}={item.value} "
            f"(confidence={item.confidence:.2f}, expires={item.expires_at})"
        )
    lines.append("</governed_memory>")
    return "\n".join(lines)


def is_contextual_follow_up(question: str) -> bool:
    """短い指代・省略質問だけを会話文脈の補完対象として判定する。"""
    normalized = re.sub(r"\s+", " ", question).strip()
    if not normalized or len(normalized) > 160:
        return False
    if any(re.search(pattern, normalized, re.I) for pattern in FOLLOW_UP_PATTERNS):
        return True
    return len(normalized) <= 60 and bool(SHORT_FOLLOW_UP_PATTERN.search(normalized))


def build_contextual_query(previous_topics: list[str], question: str) -> str:
    """検索器が指代先を復元できるよう、直近トピックと現在質問を明示的に結ぶ。"""
    topics = [topic for topic in previous_topics if topic]
    if not topics:
        return question
    lines = ["会話中の直前のトピック:"]
    lines.extend(f"- {topic}" for topic in topics)
    lines.append(f"現在の追加質問: {question}")
    return "\n".join(lines)


def _parse_topics(raw: str) -> list[str]:
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(values, list):
        return []
    return [
        _compact_topic(str(value))
        for value in values
        if str(value).strip()
    ]


def _compact_topic(question: str) -> str:
    value = SOURCE_MARKER_PATTERN.sub("", question)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:MAX_SUMMARY_TOPIC_CHARS]


def _is_memory_control_only(question: str) -> bool:
    """偏好設定・remember 指示だけの発話を業務会話摘要へ混入させない。"""
    lower = question.lower().strip()
    if any(
        marker in lower
        for marker in (
            "请记住",
            "請記住",
            "覚えておいて",
            "remember that",
        )
    ):
        return True
    preference_markers = (
        "请用中文",
        "請用中文",
        "请用日语",
        "請用日語",
        "请用英语",
        "請用英語",
        "日本語で回答",
        "中国語で回答",
        "英語で回答",
        "reply in chinese",
        "reply in japanese",
        "reply in english",
    )
    return len(lower) <= 40 and any(
        marker.lower() in lower for marker in preference_markers
    )


def _deduplicate_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    result: list[MemoryCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        identity = (candidate.kind, candidate.key)
        if identity not in seen:
            seen.add(identity)
            result.append(candidate)
    return result


def _contains_memory_poisoning(text: str) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in POISON_PATTERNS)


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _mask(
    value: str,
    pattern: re.Pattern[str],
    replacement: str,
    label: str,
    masked: list[str],
) -> str:
    if pattern.search(value):
        if label not in masked:
            masked.append(label)
        return pattern.sub(replacement, value)
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache
def get_conversation_memory_service() -> ConversationMemoryService:
    settings = get_settings()
    configured_path = Path(settings.memory_db_path)
    db_path = configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
    return ConversationMemoryService(
        db_path,
        enabled=settings.memory_enabled,
        preference_ttl_days=settings.memory_preference_ttl_days,
        fact_ttl_days=settings.memory_fact_ttl_days,
        summary_ttl_days=settings.memory_summary_ttl_days,
        summary_max_turns=settings.memory_summary_max_turns,
        max_items=settings.memory_max_items,
    )
