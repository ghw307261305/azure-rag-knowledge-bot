"""
文書切分サービス
Markdownファイルを見出し単位でチャンクに分割する
"""
import re
from pathlib import Path
from typing import List
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1600
DEFAULT_OVERLAP_CHARS = 200


@dataclass
class Chunk:
    chunk_id: str
    title: str
    section: str
    source: str
    content: str


def load_and_chunk(
    file_path: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[Chunk]:
    """
    Markdownファイルを読み込み、## 見出し単位でチャンクに分割する。
    見出しがない部分は "概要" セクションとして扱う。
    """
    text = file_path.read_text(encoding="utf-8")
    doc_title = _extract_title(text, file_path.stem)
    source = str(file_path.name)

    sections = _split_by_heading(text)
    chunks: List[Chunk] = []

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between zero and max_chars - 1")

    chunk_number = 0
    for section_name, section_content in sections:
        content = section_content.strip()
        if not content:
            continue

        for part in _split_long_content(content, max_chars, overlap_chars):
            chunk_id = f"{file_path.stem}-{chunk_number:03d}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                title=doc_title,
                section=section_name,
                source=source,
                content=part,
            ))
            chunk_number += 1

    return chunks


def _extract_title(text: str, fallback: str) -> str:
    """最初の # 見出しをドキュメントタイトルとして取得する"""
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _split_by_heading(text: str) -> List[tuple[str, str]]:
    """
    ## 見出しでテキストを分割する。
    見出し前のテキストは "概要" セクションとして扱う。
    """
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    headings = list(pattern.finditer(text))

    if not headings:
        return [("概要", text)]

    sections = []

    # 最初の ## より前のテキスト
    preamble = _remove_document_title(text[:headings[0].start()]).strip()
    if preamble:
        sections.append(("概要", preamble))

    # ## 見出しごとに分割
    for i, match in enumerate(headings):
        section_name = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        content = text[start:end].strip()
        sections.append((section_name, content))

    return sections


def _remove_document_title(text: str) -> str:
    """先頭の H1 は title metadata と重複するため本文チャンクから除外する。"""
    return re.sub(r"^#\s+.+$", "", text, count=1, flags=re.MULTILINE)


def _split_long_content(content: str, max_chars: int, overlap_chars: int) -> List[str]:
    """Split oversized sections on natural boundaries with deterministic overlap."""
    if len(content) <= max_chars:
        return [content]

    chunks: List[str] = []
    start = 0
    while start < len(content):
        target_end = min(len(content), start + max_chars)
        end = target_end
        if target_end < len(content):
            search_floor = start + max(max_chars // 2, 1)
            candidates = [
                content.rfind("\n\n", search_floor, target_end),
                content.rfind("\n", search_floor, target_end),
                content.rfind("。", search_floor, target_end),
                content.rfind(". ", search_floor, target_end),
            ]
            boundary = max(candidates)
            if boundary >= search_floor:
                end = boundary + (1 if content[boundary:boundary + 1] == "。" else 0)

        part = content[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(content):
            break

        next_start = max(end - overlap_chars, start + 1)
        while next_start < end and content[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks
