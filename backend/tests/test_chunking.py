from pathlib import Path

from app.services.chunking_service import load_and_chunk


def test_heading_only_preamble_is_not_indexed(tmp_path: Path) -> None:
    document = tmp_path / "sample.md"
    document.write_text(
        "# サンプル文書\n\n## 概要\n\n本文です。\n\n## FAQ\n\n回答です。\n",
        encoding="utf-8",
    )

    chunks = load_and_chunk(document)

    assert [chunk.section for chunk in chunks] == ["概要", "FAQ"]
    assert chunks[0].chunk_id == "sample-000"
    assert chunks[0].content == "本文です。"


def test_meaningful_preamble_is_preserved_without_duplicate_title(tmp_path: Path) -> None:
    document = tmp_path / "sample.md"
    document.write_text(
        "# サンプル文書\n\n重要な導入説明です。\n\n## 詳細\n\n詳細本文です。\n",
        encoding="utf-8",
    )

    chunks = load_and_chunk(document)

    assert chunks[0].section == "概要"
    assert chunks[0].content == "重要な導入説明です。"
    assert "# サンプル文書" not in chunks[0].content
