# Eval run 2026-09-16 16:53:12 - PASS
LLM mode: openai gpt-4o-mini

| Metric | Value | Gate | Result |
|---|---|---|---|
| leakage_violations | 0 | <= 0 | PASS |
| access_control_pass_rate | 1.0 | >= 1.0 | PASS |
| citation_validity | 1.0 | >= 1.0 | PASS |
| numeric_faithfulness | 1.0 | >= 1.0 | PASS |
| question_coverage | 1.0 | >= 1.0 | PASS |
| must_contain_recall | 1.0 | >= 0.9 | PASS |
| conflict_recall | 1.0 | >= 1.0 | PASS |
| ledger_status_accuracy | 1.0 | >= 1.0 | PASS |
| withheld_accuracy | 1.0 | >= 1.0 | PASS |
| entity_resolution_accuracy | 1.0 | >= 1.0 | PASS |
| retrieval_hit_rate_at_5 | 1.0 | >= 0.75 | PASS |
| extraction_f1 | 0.75 | >= 0.7 | PASS |
| injection_extraction_items | 0 | <= 0 | PASS |

## Operational
- briefings: 4
- latency_p50_ms: 3102.0
- latency_max_ms: 7149.0
- llm_calls: 21
- llm_tokens: 19232
- verifier_rejections: 0
- total_runtime_s: 33.7

## Case findings
- **nw-banker**: no issues
- **nw-analyst**: no issues
- **etrs-banker**: no issues
- **solstice-missing-data**: no issues