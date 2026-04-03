"""
文書切分サービス
Markdownファイルを見出し単位でチャンクに分割する
"""
import re
from pathlib import Path
from typing import List
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    title: str
    section: str
    source: str
    content: str


def load_and_chunk(file_path: Path) -> List[Chunk]:
    """
    Markdownファイルを読み込み、## 見出し単位でチャンクに分割する。
    見出しがない部分は "概要" セクションとして扱う。
    """
    text = file_path.read_text(encoding="utf-8")
    doc_title = _extract_title(text, file_path.stem)
    source = str(file_path.name)

    sections = _split_by_heading(text)
    chunks: List[Chunk] = []

    for i, (section_name, section_content) in enumerate(sections):
        content = section_content.strip()
        if not content:
            continue

        chunk_id = f"{file_path.stem}-{i:03d}"
        chunks.append(Chunk(
            chunk_id=chunk_id,
            title=doc_title,
            section=section_name,
            source=source,
            content=content,
        ))

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
    preamble = text[:headings[0].start()].strip()
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
