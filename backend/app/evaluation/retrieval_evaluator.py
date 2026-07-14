"""Deterministic evaluation for the local Markdown retrieval service."""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.local_search_service import LocalSearchService

REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "answerable",
    "expected_sources",
    "expected_keywords",
}


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    """JSONL を読み込み、評価不能な重複 ID や不足フィールドを事前に拒否する。"""
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            case = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
        missing = REQUIRED_FIELDS - case.keys()
        if missing:
            raise ValueError(
                f"Missing fields on line {line_number}: {', '.join(sorted(missing))}"
            )
        if case["id"] in seen_ids:
            raise ValueError(f"Duplicate case id: {case['id']}")
        if case["answerable"] and not case["expected_sources"]:
            raise ValueError(f"Answerable case has no expected source: {case['id']}")
        if not case["answerable"] and case["expected_sources"]:
            raise ValueError(f"Unanswerable case has expected sources: {case['id']}")
        seen_ids.add(case["id"])
        cases.append(case)
    if not cases:
        raise ValueError(f"No evaluation cases found: {dataset_path}")
    return cases


def evaluate_cases(
    cases: list[dict[str, Any]],
    search_service: LocalSearchService,
    *,
    min_score: float,
    top_k: int = 5,
) -> dict[str, Any]:
    """各ケースを実検索し、順位・フォールバック・根拠語の一致を測定する。"""
    if top_k < 5:
        raise ValueError("top_k must be at least 5 to calculate Hit@5")

    evaluated_cases: list[dict[str, Any]] = []
    for case in cases:
        started_at = time.perf_counter()
        results = search_service.search(case["question"], top_k=top_k)
        latency_ms = (time.perf_counter() - started_at) * 1000
        top_score = results[0]["score"] if results else 0.0
        predicted_answerable = bool(results and top_score >= min_score)

        expected_sources = set(case["expected_sources"])
        expected_rank = _first_expected_rank(results, expected_sources)
        matched_keywords, keyword_total = _keyword_match_counts(
            results,
            expected_sources,
            case["expected_keywords"],
        )
        keyword_coverage = (
            matched_keywords / keyword_total if keyword_total else 1.0
        )

        if case["answerable"]:
            passed = (
                predicted_answerable
                and expected_rank is not None
                and expected_rank <= 3
                and keyword_coverage == 1.0
            )
        else:
            passed = not predicted_answerable

        evaluated_cases.append(
            {
                **case,
                "predicted_answerable": predicted_answerable,
                "top_score": round(top_score, 6),
                "expected_rank": expected_rank,
                "keyword_matches": matched_keywords,
                "keyword_total": keyword_total,
                "keyword_coverage": round(keyword_coverage, 6),
                "latency_ms": round(latency_ms, 3),
                "passed": passed,
                "top_results": [
                    {
                        "rank": index + 1,
                        "source": result["source"],
                        "section": result["section"],
                        "chunk_id": result["chunk_id"],
                        "score": round(result["score"], 6),
                    }
                    for index, result in enumerate(results[:5])
                ],
            }
        )

    return _build_report(evaluated_cases, search_service, min_score, top_k)


def _first_expected_rank(
    results: list[dict], expected_sources: set[str]
) -> int | None:
    if not expected_sources:
        return None
    for index, result in enumerate(results, start=1):
        if result["source"] in expected_sources:
            return index
    return None


def _keyword_match_counts(
    results: list[dict], expected_sources: set[str], expected_keywords: list[str]
) -> tuple[int, int]:
    if not expected_keywords:
        return 0, 0
    evidence = "\n".join(
        f"{result['title']}\n{result['section']}\n{result['content']}"
        for result in results
        if result["source"] in expected_sources
    ).lower()
    matched = sum(1 for keyword in expected_keywords if keyword.lower() in evidence)
    return matched, len(expected_keywords)


def _build_report(
    evaluated_cases: list[dict[str, Any]],
    search_service: LocalSearchService,
    min_score: float,
    top_k: int,
) -> dict[str, Any]:
    """ケース結果から全体、カテゴリ別、レイテンシの集計値を構築する。"""
    answerable = [case for case in evaluated_cases if case["answerable"]]
    unanswerable = [case for case in evaluated_cases if not case["answerable"]]
    latencies = sorted(case["latency_ms"] for case in evaluated_cases)

    hit_at_1 = _hit_rate(answerable, 1)
    hit_at_3 = _hit_rate(answerable, 3)
    hit_at_5 = _hit_rate(answerable, 5)
    reciprocal_ranks = [
        1.0 / case["expected_rank"] if case["expected_rank"] else 0.0
        for case in answerable
    ]
    keyword_matches = sum(case["keyword_matches"] for case in answerable)
    keyword_total = sum(case["keyword_total"] for case in answerable)

    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in evaluated_cases:
        categories[case["category"]].append(case)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "knowledge_dir": str(search_service.knowledge_dir),
            "chunk_count": search_service.chunk_count,
            "min_score": min_score,
            "top_k": top_k,
        },
        "summary": {
            "total_cases": len(evaluated_cases),
            "answerable_cases": len(answerable),
            "unanswerable_cases": len(unanswerable),
            "passed_cases": sum(case["passed"] for case in evaluated_cases),
            "case_pass_rate": _safe_divide(
                sum(case["passed"] for case in evaluated_cases),
                len(evaluated_cases),
            ),
            "hit_at_1": hit_at_1,
            "hit_at_3": hit_at_3,
            "hit_at_5": hit_at_5,
            "mrr_at_5": _average(reciprocal_ranks),
            "fallback_accuracy": _safe_divide(
                sum(not case["predicted_answerable"] for case in unanswerable),
                len(unanswerable),
            ),
            "answerability_accuracy": _safe_divide(
                sum(
                    case["answerable"] == case["predicted_answerable"]
                    for case in evaluated_cases
                ),
                len(evaluated_cases),
            ),
            "keyword_coverage": _safe_divide(keyword_matches, keyword_total),
            "average_latency_ms": round(_average(latencies), 3),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
        },
        "categories": {
            category: {
                "cases": len(items),
                "passed": sum(item["passed"] for item in items),
                "pass_rate": _safe_divide(
                    sum(item["passed"] for item in items), len(items)
                ),
            }
            for category, items in sorted(categories.items())
        },
        "cases": evaluated_cases,
    }


def _hit_rate(cases: list[dict[str, Any]], cutoff: int) -> float:
    return _safe_divide(
        sum(
            case["expected_rank"] is not None and case["expected_rank"] <= cutoff
            for case in cases
        ),
        len(cases),
    )


def _safe_divide(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(len(values) * percentile) - 1)
    return values[index]


def render_markdown_report(
    report: dict[str, Any], thresholds: dict[str, float]
) -> str:
    """CI と人手レビューの両方で読める Markdown レポートへ変換する。"""
    summary = report["summary"]
    lines = [
        "# Finance Local Retrieval Evaluation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Configuration",
        "",
        f"- Knowledge directory: `{report['configuration']['knowledge_dir']}`",
        f"- Indexed chunks: `{report['configuration']['chunk_count']}`",
        f"- Minimum score: `{report['configuration']['min_score']}`",
        f"- Top-K: `{report['configuration']['top_k']}`",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total cases | {summary['total_cases']} |",
        f"| Answerable / Unanswerable | {summary['answerable_cases']} / {summary['unanswerable_cases']} |",
        f"| Passed cases | {summary['passed_cases']} |",
        f"| Case pass rate | {_percent(summary['case_pass_rate'])} |",
        f"| Hit@1 | {_percent(summary['hit_at_1'])} |",
        f"| Hit@3 | {_percent(summary['hit_at_3'])} |",
        f"| Hit@5 | {_percent(summary['hit_at_5'])} |",
        f"| MRR@5 | {summary['mrr_at_5']:.4f} |",
        f"| Fallback accuracy | {_percent(summary['fallback_accuracy'])} |",
        f"| Answerability accuracy | {_percent(summary['answerability_accuracy'])} |",
        f"| Keyword coverage | {_percent(summary['keyword_coverage'])} |",
        f"| Average / P95 latency | {summary['average_latency_ms']:.3f} / {summary['p95_latency_ms']:.3f} ms |",
        "",
        "## Quality Gates",
        "",
        "| Gate | Required | Actual | Result |",
        "|---|---:|---:|---|",
    ]
    for metric, required in thresholds.items():
        actual = summary[metric]
        result = "PASS" if actual >= required else "FAIL"
        lines.append(
            f"| {metric} | {_percent(required)} | {_percent(actual)} | {result} |"
        )

    lines.extend(
        [
            "",
            "## Category Results",
            "",
            "| Category | Cases | Passed | Pass rate |",
            "|---|---:|---:|---:|",
        ]
    )
    for category, result in report["categories"].items():
        lines.append(
            f"| {category} | {result['cases']} | {result['passed']} | {_percent(result['pass_rate'])} |"
        )

    failures = [case for case in report["cases"] if not case["passed"]]
    lines.extend(["", "## Failed Cases", ""])
    if not failures:
        lines.append("No failed cases.")
    else:
        lines.extend(
            [
                "| ID | Category | Question | Expected rank | Top source | Score | Keyword coverage |",
                "|---|---|---|---:|---|---:|---:|",
            ]
        )
        for case in failures:
            top_source = (
                case["top_results"][0]["source"] if case["top_results"] else "-"
            )
            rank = case["expected_rank"] or "-"
            question = case["question"].replace("|", "\\|")
            lines.append(
                f"| {case['id']} | {case['category']} | {question} | {rank} | "
                f"{top_source} | {case['top_score']:.4f} | {_percent(case['keyword_coverage'])} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Hit@K and MRR evaluate whether the expected source appears near the top.",
            "- Fallback accuracy evaluates whether out-of-scope questions remain below the score threshold.",
            "- Keyword coverage checks whether retrieved evidence contains the annotated answer cues.",
            "- This report evaluates retrieval only; generated-answer quality is evaluated after a local or Azure LLM is connected.",
            "",
        ]
    )
    return "\n".join(lines)


def quality_gates_pass(
    report: dict[str, Any], thresholds: dict[str, float]
) -> bool:
    return all(report["summary"][metric] >= minimum for metric, minimum in thresholds.items())


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
