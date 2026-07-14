"""Azure に接続せず、Markdown ナレッジを検索するローカル検索サービス。"""

import math
import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock

from app.services.chunking_service import Chunk, load_and_chunk
from app.services.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_QUERY_PHRASES = (
    "教えてください",
    "してください",
    "何ですか",
    "ありますか",
    "できますか",
    "について",
    "教えて",
    "ですか",
    "ますか",
)


@dataclass(frozen=True)
class _IndexedChunk:
    chunk: Chunk
    weights: dict[str, float]
    norm: float
    title_terms: frozenset[str]
    section_terms: frozenset[str]
    department: str
    security_level: str
    allowed_groups: frozenset[str]


class LocalSearchService:
    """文字 n-gram TF-IDF で日本語 Markdown をインメモリ検索する。"""

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self.knowledge_dir = knowledge_dir or _resolve_knowledge_dir()
        self._lock = RLock()
        self._documents: list[_IndexedChunk] = []
        self._idf: dict[str, float] = {}
        self.rebuild()

    @property
    def chunk_count(self) -> int:
        with self._lock:
            return len(self._documents)

    def rebuild(self) -> int:
        access_control = _load_access_control(self.knowledge_dir)
        chunks: list[Chunk] = []
        for file_path in sorted(self.knowledge_dir.glob("*.md")):
            chunks.extend(load_and_chunk(file_path))

        term_counts: list[Counter[str]] = []
        document_frequency: Counter[str] = Counter()
        for chunk in chunks:
            searchable_text = (
                f"{chunk.title} {chunk.title} "
                f"{chunk.section} {chunk.section} {chunk.content}"
            )
            counts = Counter(_extract_terms(searchable_text))
            term_counts.append(counts)
            document_frequency.update(counts.keys())

        document_count = len(chunks)
        idf = {
            term: math.log((document_count + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }

        documents: list[_IndexedChunk] = []
        for chunk, counts in zip(chunks, term_counts):
            metadata = _document_access_metadata(access_control, chunk.source)
            weights = _tf_idf_weights(counts, idf)
            norm = math.sqrt(sum(weight * weight for weight in weights.values()))
            documents.append(
                _IndexedChunk(
                    chunk=chunk,
                    weights=weights,
                    norm=norm,
                    title_terms=frozenset(_extract_terms(chunk.title)),
                    section_terms=frozenset(_extract_terms(chunk.section)),
                    department=str(metadata.get("department", "unspecified")),
                    security_level=str(metadata.get("security_level", "internal")),
                    allowed_groups=frozenset(metadata.get("allowed_groups", [])),
                )
            )

        with self._lock:
            self._documents = documents
            self._idf = idf
        return len(documents)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        allowed_groups: set[str] | None = None,
    ) -> list[dict]:
        if top_k <= 0:
            return []

        query_counts = Counter(_extract_terms(query))
        with self._lock:
            documents = list(self._documents)
            idf = dict(self._idf)

        if not query_counts or not documents:
            return []

        unseen_idf = math.log(len(documents) + 1) + 1.0
        query_weights = {
            term: (1.0 + math.log(count)) * idf.get(term, unseen_idf)
            for term, count in query_counts.items()
        }
        query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values()))
        if query_norm == 0:
            return []

        query_terms = frozenset(query_weights)
        scored: list[tuple[float, Chunk, _IndexedChunk]] = []
        for document in documents:
            if not _can_access(document.allowed_groups, allowed_groups):
                continue
            if document.norm == 0:
                continue
            dot_product = sum(
                query_weight * document.weights.get(term, 0.0)
                for term, query_weight in query_weights.items()
            )
            cosine_score = dot_product / (query_norm * document.norm)
            title_score = _dice_overlap(query_terms, document.title_terms)
            section_score = _dice_overlap(query_terms, document.section_terms)
            score = min(
                1.0,
                cosine_score + (0.25 * title_score) + (0.10 * section_score),
            )
            if score > 0:
                scored.append((score, document.chunk, document))

        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [
            {
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "section": chunk.section,
                "source": chunk.source,
                "content": chunk.content,
                "score": score,
                "department": document.department,
                "security_level": document.security_level,
                "allowed_groups": sorted(document.allowed_groups),
            }
            for score, chunk, document in scored[:top_k]
        ]


def _load_access_control(knowledge_dir: Path) -> dict:
    metadata_path = knowledge_dir / "access-control.json"
    if not metadata_path.exists():
        return {"default": {"allowed_groups": ["*"]}, "documents": {}}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid access-control.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("access-control.json must contain a JSON object")
    return payload


def _document_access_metadata(access_control: dict, source: str) -> dict:
    default = access_control.get("default", {})
    documents = access_control.get("documents", {})
    override = documents.get(source, {}) if isinstance(documents, dict) else {}
    metadata = {**default, **override}
    groups = metadata.get("allowed_groups", ["*"])
    if not isinstance(groups, list) or not all(isinstance(item, str) for item in groups):
        raise ValueError(f"allowed_groups must be a string list for {source}")
    metadata["allowed_groups"] = [item.strip() for item in groups if item.strip()]
    return metadata


def _can_access(
    document_groups: frozenset[str], allowed_groups: set[str] | None
) -> bool:
    if allowed_groups is None or "*" in allowed_groups or "*" in document_groups:
        return True
    return bool(document_groups & allowed_groups)


def _tf_idf_weights(
    counts: Counter[str], idf: dict[str, float]
) -> dict[str, float]:
    return {
        term: (1.0 + math.log(count)) * idf[term]
        for term, count in counts.items()
    }


def _dice_overlap(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return (2.0 * len(left & right)) / (len(left) + len(right))


def _extract_terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    for phrase in COMMON_QUERY_PHRASES:
        normalized = normalized.replace(phrase, "")
    compact = "".join(
        character
        for character in normalized
        if unicodedata.category(character)[0] in {"L", "N"}
    )
    if not compact:
        return []

    terms: list[str] = []
    for size in (2, 3):
        terms.extend(
            compact[index:index + size]
            for index in range(max(0, len(compact) - size + 1))
        )
    if len(compact) == 1:
        terms.append(compact)
    return terms


def _resolve_knowledge_dir() -> Path:
    configured_path = Path(get_settings().knowledge_dir)
    if configured_path.is_absolute():
        return configured_path
    return (REPO_ROOT / configured_path).resolve()


@lru_cache
def get_local_search_service() -> LocalSearchService:
    return LocalSearchService()
