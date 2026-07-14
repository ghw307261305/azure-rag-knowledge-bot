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


def test_long_section_is_split_with_overlap_and_stable_ids(tmp_path: Path) -> None:
    document = tmp_path / "long.md"
    document.write_text(
        "# 長文\n\n## 手順\n\n" + "第一段落です。" * 15 + "\n\n" + "第二段落です。" * 15,
        encoding="utf-8",
    )

    chunks = load_and_chunk(document, max_chars=100, overlap_chars=20)

    assert len(chunks) >= 3
    assert [chunk.chunk_id for chunk in chunks] == [
        f"long-{index:03d}" for index in range(len(chunks))
    ]
    assert all(len(chunk.content) <= 100 for chunk in chunks)
    assert all(chunk.section == "手順" for chunk in chunks)
    assert any(chunks[index].content[-10:] in chunks[index + 1].content for index in range(len(chunks) - 1))


def test_invalid_chunk_limits_are_rejected(tmp_path: Path) -> None:
    document = tmp_path / "sample.md"
    document.write_text("# 文書\n\n本文", encoding="utf-8")

    try:
        load_and_chunk(document, max_chars=100, overlap_chars=100)
    except ValueError as error:
        assert "overlap_chars" in str(error)
    else:
        raise AssertionError("invalid overlap must be rejected")
