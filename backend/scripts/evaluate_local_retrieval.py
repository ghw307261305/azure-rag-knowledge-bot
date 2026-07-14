"""Run the finance local-retrieval evaluation and write JSON/Markdown reports."""

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.retrieval_evaluator import (  # noqa: E402
    evaluate_cases,
    load_cases,
    quality_gates_pass,
    render_markdown_report,
)
from app.services.local_search_service import LocalSearchService  # noqa: E402

DEFAULT_DATASET = BACKEND_ROOT / "evaluation" / "finance_questions.jsonl"
DEFAULT_KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge-finance"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "evaluation"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate local finance document retrieval quality"
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-score", type=float, default=0.06)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-hit-at-3", type=float, default=0.90)
    parser.add_argument("--min-fallback-accuracy", type=float, default=0.95)
    parser.add_argument("--min-keyword-coverage", type=float, default=0.90)
    parser.add_argument("--min-answerability-accuracy", type=float, default=0.95)
    args = parser.parse_args()

    thresholds = {
        "hit_at_3": args.min_hit_at_3,
        "fallback_accuracy": args.min_fallback_accuracy,
        "keyword_coverage": args.min_keyword_coverage,
        "answerability_accuracy": args.min_answerability_accuracy,
    }
    cases = load_cases(args.dataset.resolve())
    search_service = LocalSearchService(args.knowledge_dir.resolve())
    report = evaluate_cases(
        cases,
        search_service,
        min_score=args.min_score,
        top_k=args.top_k,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "finance-retrieval-report.json"
    markdown_path = args.output_dir / "finance-retrieval-report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_markdown_report(report, thresholds),
        encoding="utf-8",
    )

    summary = report["summary"]
    print(f"Cases: {summary['passed_cases']}/{summary['total_cases']} passed")
    print(f"Hit@3: {summary['hit_at_3']:.1%}")
    print(f"Fallback accuracy: {summary['fallback_accuracy']:.1%}")
    print(f"Keyword coverage: {summary['keyword_coverage']:.1%}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if quality_gates_pass(report, thresholds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
