import json

import pytest

from app.evaluation.generation_evaluator import (
    evaluate_generation_cases,
    load_generation_cases,
    quality_gates_pass,
    render_generation_report,
)


def _cases() -> list[dict]:
    return [
        {
            "id": "ANSWER-1",
            "category": "transfer",
            "question": "answer",
            "expected_behavior": "answer",
            "expected_sources": ["transfer.md"],
            "required_concepts": [
                ["RECEIVED"],
                ["組戻しになります", "組戻しとして"],
            ],
            "forbidden_terms": ["必ず返金"],
        },
        {
            "id": "REFUSE-1",
            "category": "refusal",
            "question": "refuse",
            "expected_behavior": "refuse",
            "expected_sources": [],
            "required_concepts": [],
            "forbidden_terms": [],
            "refusal_phrases": ["見つかりません"],
        },
        {
            "id": "BLOCK-1",
            "category": "safety",
            "question": "block",
            "expected_behavior": "block",
            "expected_sources": [],
            "required_concepts": [],
            "forbidden_terms": [],
            "expected_status": 400,
        },
    ]


def _provider(question: str) -> dict:
    if question == "answer":
        return {
            "status_code": 200,
            "latency_ms": 1200,
            "body": {
                "answer": (
                    "RECEIVED の間は取消可能です。"
                    "実行後は組戻しになります。[S1]"
                ),
                "citations": [
                    {
                        "title": "[S1] transfer.md / FAQ",
                        "chunk_id": "transfer-1",
                        "content": (
                            "RECEIVED の間は取消可能です。"
                            "実行後は組戻しとして扱います。"
                        ),
                    }
                ],
                "fallback_used": False,
                "rag_mode": "local_llm",
                "model": "gemma3:4b-it-qat",
                "token_usage": {"total_tokens": 100},
            },
        }
    if question == "refuse":
        return {
            "status_code": 200,
            "latency_ms": 2,
            "body": {
                "answer": "関連する情報が見つかりませんでした。",
                "citations": [],
                "fallback_used": True,
                "token_usage": {"total_tokens": 0},
            },
        }
    return {
        "status_code": 400,
        "latency_ms": 1,
        "body": {"detail": "不正なリクエストが検出されました"},
    }


def test_generation_evaluator_passes_grounded_refusal_and_safety_cases() -> None:
    report = evaluate_generation_cases(_cases(), _provider)
    summary = report["summary"]

    assert summary["passed_cases"] == 3
    assert summary["generation_success_rate"] == 1.0
    assert summary["citation_validity_rate"] == 1.0
    assert summary["citation_coverage"] == 1.0
    assert summary["grounded_concept_coverage"] == 1.0
    assert summary["numeric_grounding_rate"] == 1.0
    assert summary["refusal_accuracy"] == 1.0
    assert summary["safety_block_rate"] == 1.0
    assert quality_gates_pass(report, {"case_pass_rate": 1.0})
    assert "No failed cases" in render_generation_report(
        report, {"case_pass_rate": 1.0}
    )


def test_generation_evaluator_rejects_unmapped_citation_and_invented_number() -> None:
    cases = [_cases()[0]]

    def invalid_provider(question: str) -> dict:
        response = _provider(question)
        response["body"]["answer"] = (
            "RECEIVED の間は24時間取消可能です。[S2] 組戻しになります。[S2]"
        )
        return response

    result = evaluate_generation_cases(cases, invalid_provider)["cases"][0]

    assert result["citation_valid"] is False
    assert result["unsupported_numbers"] == ["24"]
    assert result["passed"] is False


def test_load_generation_cases_validates_schema(tmp_path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(_cases()[0], ensure_ascii=False) + "\n", encoding="utf-8"
    )

    loaded = load_generation_cases(dataset)
    assert loaded[0]["id"] == "ANSWER-1"

    dataset.write_text(
        json.dumps({"id": "missing"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing fields"):
        load_generation_cases(dataset)
