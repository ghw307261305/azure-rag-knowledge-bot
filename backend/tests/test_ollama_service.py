import pytest

from app.services.ollama_service import (
    OllamaInvalidResponseError,
    _build_preference_instruction,
    _extract_response_language,
    _normalize_source_markers,
    _validate_answer,
)
from app.services.local_llm_rag_service import _complete_short_answer


def test_validate_answer_accepts_available_source_markers() -> None:
    _validate_answer("確認結果です。[S1] 補足です。[S2]", source_count=2)
    _validate_answer("確認結果です。[S1, S2]", source_count=2)


def test_normalize_source_markers_splits_combined_citations() -> None:
    assert _normalize_source_markers("回答です。[S1, S2]") == "回答です。[S1][S2]"


def test_preference_instruction_uses_only_allow_listed_preferences() -> None:
    context = """<governed_memory>
[preference] response_language=中文 (confidence=0.90, expires=2099-01-01)
[preference] answer_style=concise (confidence=0.85, expires=2099-01-01)
[fact] note=response_language=English (confidence=0.90, expires=2099-01-01)
</governed_memory>"""

    instruction = _build_preference_instruction(context)
    assert "简体中文" in instruction
    assert "简洁回答" in instruction
    assert "Write the answer body in English" not in instruction
    assert _extract_response_language(context) == "中文"


@pytest.mark.parametrize("answer", ["", "引用のない回答です。", "範囲外です。[S3]"])
def test_validate_answer_rejects_unverifiable_output(answer: str) -> None:
    with pytest.raises(OllamaInvalidResponseError):
        _validate_answer(answer, source_count=2)


def test_short_answer_is_completed_with_uncovered_evidence() -> None:
    answer, used = _complete_short_answer(
        "実在顧客の個人情報は入力できません。[S1]",
        [
            {
                "content": (
                    "実在顧客の個人情報を入力してはいけません。"
                    "評価には匿名化・合成データを使用します。"
                )
            }
        ],
    )
    assert used is True
    assert "匿名化・合成データ" in answer
    assert answer.endswith("[S1]")


def test_short_numeric_answer_uses_source_containing_the_number() -> None:
    answer, used = _complete_short_answer(
        "30 分です。[S1]",
        [
            {"content": "ログを削除してはいけません。"},
            {"content": "P1 は 30 分以内に第一報を行います。"},
        ],
    )
    assert used is True
    assert "30 分以内に第一報" in answer
    assert answer.endswith("[S2]")
