# Finance Local Retrieval Evaluation Report

Generated at: `2026-07-14T03:06:21.514209+00:00`

## Configuration

- Knowledge directory: `C:\rigelsoft\workspace\azure-rag-knowledge-bot\docs\knowledge-finance`
- Indexed chunks: `142`
- Minimum score: `0.06`
- Top-K: `5`

## Summary

| Metric | Result |
|---|---:|
| Total cases | 88 |
| Answerable / Unanswerable | 76 / 12 |
| Passed cases | 88 |
| Case pass rate | 100.0% |
| Hit@1 | 90.8% |
| Hit@3 | 100.0% |
| Hit@5 | 100.0% |
| MRR@5 | 0.9518 |
| Fallback accuracy | 100.0% |
| Answerability accuracy | 100.0% |
| Keyword coverage | 100.0% |
| Average / P95 latency | 2.446 / 3.455 ms |

## Quality Gates

| Gate | Required | Actual | Result |
|---|---:|---:|---|
| hit_at_3 | 90.0% | 100.0% | PASS |
| fallback_accuracy | 95.0% | 100.0% | PASS |
| keyword_coverage | 90.0% | 100.0% | PASS |
| answerability_accuracy | 95.0% | 100.0% | PASS |

## Category Results

| Category | Cases | Passed | Pass rate |
|---|---:|---:|---:|
| account | 3 | 3 | 100.0% |
| aml | 4 | 4 | 100.0% |
| atm | 1 | 1 | 100.0% |
| bcp | 2 | 2 | 100.0% |
| card_loss | 1 | 1 | 100.0% |
| complaint | 2 | 2 | 100.0% |
| contact_center | 1 | 1 | 100.0% |
| corporate_banking | 2 | 2 | 100.0% |
| credit_paraphrase | 1 | 1 | 100.0% |
| credit_risk | 3 | 3 | 100.0% |
| customer_profile | 2 | 2 | 100.0% |
| cyber_paraphrase | 1 | 1 | 100.0% |
| cybersecurity | 2 | 2 | 100.0% |
| data_entry_safety | 1 | 1 | 100.0% |
| data_protection | 3 | 3 | 100.0% |
| delinquency | 3 | 3 | 100.0% |
| fraud | 3 | 3 | 100.0% |
| fx_rate_boundary | 2 | 2 | 100.0% |
| governance | 1 | 1 | 100.0% |
| governance_escalation | 1 | 1 | 100.0% |
| governance_paraphrase | 1 | 1 | 100.0% |
| international_remittance | 2 | 2 | 100.0% |
| internet_banking | 2 | 2 | 100.0% |
| knowledge_update_paraphrase | 1 | 1 | 100.0% |
| kyc | 3 | 3 | 100.0% |
| legacy_recruitment | 2 | 2 | 100.0% |
| loan_underwriting | 4 | 4 | 100.0% |
| product_suitability | 3 | 3 | 100.0% |
| regulatory_change | 3 | 3 | 100.0% |
| regulatory_paraphrase | 1 | 1 | 100.0% |
| retail_product | 2 | 2 | 100.0% |
| suspicious_transaction | 3 | 3 | 100.0% |
| time_deposit | 2 | 2 | 100.0% |
| transfer | 4 | 4 | 100.0% |
| transfer_fee | 1 | 1 | 100.0% |
| transfer_limit | 1 | 1 | 100.0% |
| transfer_refund | 3 | 3 | 100.0% |
| transfer_service_hours | 1 | 1 | 100.0% |
| unanswerable_advice | 1 | 1 | 100.0% |
| unanswerable_insurance | 1 | 1 | 100.0% |
| unanswerable_legal | 1 | 1 | 100.0% |
| unanswerable_market | 2 | 2 | 100.0% |
| unanswerable_other | 2 | 2 | 100.0% |
| unanswerable_pension | 1 | 1 | 100.0% |
| unanswerable_product | 1 | 1 | 100.0% |
| unanswerable_tax | 1 | 1 | 100.0% |

## Failed Cases

No failed cases.

## Interpretation

- Hit@K and MRR evaluate whether the expected source appears near the top.
- Fallback accuracy evaluates whether out-of-scope questions remain below the score threshold.
- Keyword coverage checks whether retrieved evidence contains the annotated answer cues.
- This report evaluates retrieval only; generated-answer quality is evaluated after a local or Azure LLM is connected.
