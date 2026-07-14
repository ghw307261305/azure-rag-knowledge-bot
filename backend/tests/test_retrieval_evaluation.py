from pathlib import Path

from app.evaluation.retrieval_evaluator import (
    evaluate_cases,
    load_cases,
    render_markdown_report,
)
from app.services.local_search_service import LocalSearchService

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "backend" / "evaluation" / "finance_questions.jsonl"
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge-finance"


def test_finance_retrieval_quality_gates() -> None:
    cases = load_cases(DATASET_PATH)
    report = evaluate_cases(
        cases,
        LocalSearchService(KNOWLEDGE_DIR),
        min_score=0.06,
        top_k=5,
    )
    summary = report["summary"]

    assert summary["total_cases"] == 88
    assert summary["hit_at_3"] >= 0.90
    assert summary["fallback_accuracy"] >= 0.95
    assert summary["answerability_accuracy"] >= 0.95
    assert summary["keyword_coverage"] >= 0.90
    assert summary["passed_cases"] == summary["total_cases"]


def test_markdown_report_contains_quality_gates() -> None:
    cases = load_cases(DATASET_PATH)
    report = evaluate_cases(
        cases,
        LocalSearchService(KNOWLEDGE_DIR),
        min_score=0.06,
        top_k=5,
    )
    markdown = render_markdown_report(
        report,
        {
            "hit_at_3": 0.90,
            "fallback_accuracy": 0.95,
            "keyword_coverage": 0.90,
            "answerability_accuracy": 0.95,
        },
    )

    assert "## Quality Gates" in markdown
    assert "No failed cases." in markdown
