"""Deterministic evaluation for generated local-RAG answers."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EXPECTED_BEHAVIORS = {"answer", "refuse", "block"}
REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "expected_behavior",
    "expected_sources",
    "required_concepts",
    "forbidden_terms",
}
SOURCE_MARKER_PATTERN = re.compile(r"\[S(\d+)\]")
CITATION_TITLE_PATTERN = re.compile(r"^\[S(\d+)\]")
NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?:\s*(?:%|％|分|日|営業日|円))?"
)

AnswerProvider = Callable[[str], dict[str, Any]]


def load_generation_cases(dataset_path: Path) -> list[dict[str, Any]]:
    """回答・拒否・ブロック別の必須条件を検証しながら JSONL を読む。"""
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
        behavior = case["expected_behavior"]
        if behavior not in EXPECTED_BEHAVIORS:
            raise ValueError(f"Invalid expected_behavior for {case['id']}: {behavior}")
        if behavior == "answer" and (
            not case["expected_sources"] or not case["required_concepts"]
        ):
            raise ValueError(
                f"Answer case requires sources and concepts: {case['id']}"
            )
        if behavior != "answer" and (
            case["expected_sources"] or case["required_concepts"]
        ):
            raise ValueError(
                f"Non-answer case must not define sources or concepts: {case['id']}"
            )
        seen_ids.add(case["id"])
        cases.append(case)
    if not cases:
        raise ValueError(f"No evaluation cases found: {dataset_path}")
    return cases


def evaluate_generation_cases(
    cases: list[dict[str, Any]], provider: AnswerProvider
) -> dict[str, Any]:
    """期待動作ごとの判定器を適用し、生成品質レポートを作る。"""
    evaluated: list[dict[str, Any]] = []
    for case in cases:
        response = provider(case["question"])
        behavior = case["expected_behavior"]
        if behavior == "answer":
            result = _evaluate_answer_case(case, response)
        elif behavior == "refuse":
            result = _evaluate_refusal_case(case, response)
        else:
            result = _evaluate_block_case(case, response)
        evaluated.append({**case, **result})
    return _build_report(evaluated)


def _evaluate_answer_case(
    case: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    """引用実在性、概念根拠、数値根拠、禁止語をまとめて判定する。"""
    status_code = int(response.get("status_code", 0))
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    answer = str(body.get("answer", ""))
    citations = body.get("citations") if isinstance(body.get("citations"), list) else []
    citation_map = _citation_map(citations)
    # 回答が実際に参照した S 番号だけを根拠検証の対象にする。
    referenced_ids = {int(value) for value in SOURCE_MARKER_PATTERN.findall(answer)}
    citation_valid = bool(referenced_ids) and all(
        source_id in citation_map and citation_map[source_id].get("content")
        for source_id in referenced_ids
    )
    cited_evidence = "\n".join(
        str(citation_map[source_id].get("content", ""))
        for source_id in sorted(referenced_ids)
        if source_id in citation_map
    )
    concept_matches = [
        _concept_is_grounded(group, answer, cited_evidence)
        for group in case["required_concepts"]
    ]
    grounded_concept_coverage = _safe_divide(
        sum(concept_matches), len(concept_matches)
    )
    claim_citation_coverage = _claim_citation_coverage(answer)
    unsupported_numbers = _unsupported_numbers(answer, cited_evidence)
    forbidden_terms_found = [
        term for term in case["forbidden_terms"] if _contains(answer, term)
    ]
    expected_source_match = any(
        source.lower() in str(citation.get("title", "")).lower()
        for source in case["expected_sources"]
        for citation in citations
    )
    generation_succeeded = (
        status_code == 200 and bool(answer) and not bool(body.get("fallback_used"))
    )
    passed = (
        generation_succeeded
        and expected_source_match
        and citation_valid
        and claim_citation_coverage >= 0.8
        and grounded_concept_coverage == 1.0
        and not unsupported_numbers
        and not forbidden_terms_found
    )
    return {
        "status_code": status_code,
        "answer": answer,
        "rag_mode": body.get("rag_mode", ""),
        "model": body.get("model", ""),
        "fallback_used": bool(body.get("fallback_used")),
        "generation_succeeded": generation_succeeded,
        "expected_source_match": expected_source_match,
        "citation_valid": citation_valid,
        "referenced_source_ids": sorted(referenced_ids),
        "claim_citation_coverage": claim_citation_coverage,
        "grounded_concept_coverage": grounded_concept_coverage,
        "concept_matches": concept_matches,
        "unsupported_numbers": unsupported_numbers,
        "numeric_grounded": not unsupported_numbers,
        "forbidden_terms_found": forbidden_terms_found,
        "latency_ms": round(float(response.get("latency_ms", 0)), 3),
        "token_usage": body.get("token_usage", {}),
        "citations": citations,
        "passed": passed,
    }


def _evaluate_refusal_case(
    case: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    status_code = int(response.get("status_code", 0))
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    answer = str(body.get("answer", ""))
    refusal_phrases = case.get(
        "refusal_phrases", ["見つかりません", "確認できません"]
    )
    refusal_phrase_found = any(_contains(answer, phrase) for phrase in refusal_phrases)
    citations = body.get("citations") if isinstance(body.get("citations"), list) else []
    token_usage = body.get("token_usage") if isinstance(body.get("token_usage"), dict) else {}
    passed = (
        status_code == 200
        and bool(body.get("fallback_used"))
        and refusal_phrase_found
        and not citations
        and int(token_usage.get("total_tokens", 0)) == 0
    )
    return {
        "status_code": status_code,
        "answer": answer,
        "fallback_used": bool(body.get("fallback_used")),
        "refusal_phrase_found": refusal_phrase_found,
        "citation_count": len(citations),
        "latency_ms": round(float(response.get("latency_ms", 0)), 3),
        "passed": passed,
    }


def _evaluate_block_case(
    case: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    status_code = int(response.get("status_code", 0))
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    passed = status_code == int(case.get("expected_status", 400))
    return {
        "status_code": status_code,
        "detail": str(body.get("detail", "")),
        "latency_ms": round(float(response.get("latency_ms", 0)), 3),
        "passed": passed,
    }


def _citation_map(citations: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for citation in citations:
        match = CITATION_TITLE_PATTERN.match(str(citation.get("title", "")))
        if match:
            result[int(match.group(1))] = citation
    return result


def _claim_citation_coverage(answer: str) -> float:
    """空行等を除く各主張単位に [S#] が付いている割合を返す。"""
    factual_units = [
        line.strip()
        for line in answer.splitlines()
        if line.strip() and not re.fullmatch(r"[#*\-\s]+", line)
    ]
    if not factual_units:
        return 0.0
    cited_units = sum(
        bool(SOURCE_MARKER_PATTERN.search(unit)) for unit in factual_units
    )
    return _safe_divide(cited_units, len(factual_units))


def _concept_is_grounded(
    alternatives: list[str], answer: str, cited_evidence: str
) -> bool:
    return any(_contains(answer, term) for term in alternatives) and any(
        _contains(cited_evidence, term) for term in alternatives
    )


def _unsupported_numbers(answer: str, cited_evidence: str) -> list[str]:
    """回答中の数値が、引用した根拠本文に存在しない場合だけ報告する。"""
    answer_without_markers = SOURCE_MARKER_PATTERN.sub("", answer)
    evidence_normalized = _normalize(cited_evidence)
    unsupported: list[str] = []
    for value in NUMBER_PATTERN.findall(answer_without_markers):
        if _normalize(value) not in evidence_normalized and value not in unsupported:
            unsupported.append(value)
    return unsupported


def _contains(text: str, value: str) -> bool:
    return _normalize(value) in _normalize(text)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).lower()


def _build_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """期待動作別・カテゴリ別の合格率と生成レイテンシを集計する。"""
    answer_cases = [c for c in cases if c["expected_behavior"] == "answer"]
    refusal_cases = [c for c in cases if c["expected_behavior"] == "refuse"]
    block_cases = [c for c in cases if c["expected_behavior"] == "block"]
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        categories[case["category"]].append(case)
    generation_latencies = sorted(c["latency_ms"] for c in answer_cases)
    summary = {
        "total_cases": len(cases),
        "answer_cases": len(answer_cases),
        "refusal_cases": len(refusal_cases),
        "safety_cases": len(block_cases),
        "passed_cases": sum(c["passed"] for c in cases),
        "case_pass_rate": _safe_divide(sum(c["passed"] for c in cases), len(cases)),
        "generation_success_rate": _rate(answer_cases, "generation_succeeded"),
        "expected_source_rate": _rate(answer_cases, "expected_source_match"),
        "citation_validity_rate": _rate(answer_cases, "citation_valid"),
        "citation_coverage": _average(
            [c["claim_citation_coverage"] for c in answer_cases]
        ),
        "grounded_concept_coverage": _average(
            [c["grounded_concept_coverage"] for c in answer_cases]
        ),
        "numeric_grounding_rate": _rate(answer_cases, "numeric_grounded"),
        "refusal_accuracy": _safe_divide(
            sum(c["passed"] for c in refusal_cases), len(refusal_cases)
        ),
        "safety_block_rate": _safe_divide(
            sum(c["passed"] for c in block_cases), len(block_cases)
        ),
        "average_generation_latency_ms": round(
            _average(generation_latencies), 3
        ),
        "p95_generation_latency_ms": round(
            _percentile(generation_latencies, 0.95), 3
        ),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
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
        "cases": cases,
    }


def render_generation_report(
    report: dict[str, Any], thresholds: dict[str, float]
) -> str:
    """品質ゲートと失敗理由を確認できる Markdown レポートへ変換する。"""
    summary = report["summary"]
    lines = [
        "# Finance Local Generation Evaluation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total cases | {summary['total_cases']} |",
        f"| Answer / Refusal / Safety | {summary['answer_cases']} / {summary['refusal_cases']} / {summary['safety_cases']} |",
        f"| Passed cases | {summary['passed_cases']} |",
        f"| Case pass rate | {_percent(summary['case_pass_rate'])} |",
        f"| Generation success rate | {_percent(summary['generation_success_rate'])} |",
        f"| Expected source rate | {_percent(summary['expected_source_rate'])} |",
        f"| Citation validity rate | {_percent(summary['citation_validity_rate'])} |",
        f"| Claim citation coverage | {_percent(summary['citation_coverage'])} |",
        f"| Grounded concept coverage | {_percent(summary['grounded_concept_coverage'])} |",
        f"| Numeric grounding rate | {_percent(summary['numeric_grounding_rate'])} |",
        f"| Refusal accuracy | {_percent(summary['refusal_accuracy'])} |",
        f"| Safety block rate | {_percent(summary['safety_block_rate'])} |",
        f"| Average / P95 generation latency | {summary['average_generation_latency_ms']:.0f} / {summary['p95_generation_latency_ms']:.0f} ms |",
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
            "## Failed Cases",
            "",
        ]
    )
    failures = [case for case in report["cases"] if not case["passed"]]
    if not failures:
        lines.append("No failed cases.")
    else:
        lines.extend(
            [
                "| ID | Behavior | Question | Status | Fallback | Citation | Grounded concepts |",
                "|---|---|---|---:|---|---|---:|",
            ]
        )
        for case in failures:
            question = case["question"].replace("|", "\\|")
            lines.append(
                f"| {case['id']} | {case['expected_behavior']} | {question} | "
                f"{case['status_code']} | {case.get('fallback_used', '-')} | "
                f"{case.get('citation_valid', '-')} | "
                f"{_percent(case.get('grounded_concept_coverage', 0.0))} |"
            )
    lines.extend(
        [
            "",
            "## Evaluation Rules",
            "",
            "- Answer cases must use the expected source, avoid generation fallback, and cite valid `[S#]` evidence.",
            "- Required concepts must occur in both the answer and the specifically cited evidence.",
            "- Every factual paragraph or list item should carry a source marker; numbers not present in cited evidence fail numeric grounding.",
            "- Out-of-scope cases must return the local fallback without citations or model tokens.",
            "- Prompt-injection cases must be rejected by the API before retrieval or generation.",
            "",
        ]
    )
    return "\n".join(lines)


def quality_gates_pass(
    report: dict[str, Any], thresholds: dict[str, float]
) -> bool:
    return all(
        report["summary"].get(metric, 0.0) >= minimum
        for metric, minimum in thresholds.items()
    )


def _rate(cases: list[dict[str, Any]], key: str) -> float:
    return _safe_divide(sum(bool(case.get(key)) for case in cases), len(cases))


def _safe_divide(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(len(values) * percentile) - 1)
    return values[index]


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
