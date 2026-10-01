# Context Assembly 2.0

`ContextEngine.build_context` is extended, not replaced. Default
construction behaves exactly as before (same ranking, same 512-token
word-count budget); passing `budget_config=` (constructor or per call)
enables Phase F behavior.

## Priority classes (`cognition/context/priority.py`)

CRITICAL (request/task/system — never dropped for size) / IMPORTANT /
RELEVANT / OPTIONAL / DISCARDABLE (below the 0.15 relevance floor).
Classification is deterministic from source + attention/relevance.

## Budgets (`BudgetConfig`)

- `total_tokens`: hard selection budget in rank order.
- `per_source_tokens`: e.g. cap `memory` so one source cannot evict all others.
- `protected`: classes exempt from caps (default CRITICAL).
- `compress`: over-budget protected items are truncated to fit rather
  than dropped; lowest-priority selections compress next.

Every removal, kept-over-budget, and compression is appended to
`diagnostics` with source, priority, and reason; the payload exposes
`priorities` and `diagnostics` alongside `observability`.

## Ranking inputs per item

relevance, recency, importance, confidence, source quality (via
relationship weight), task relationship — scored by the existing
`AttentionEngine` weights, then FILTER → DEDUPLICATE → COMPRESS →
BUDGET → ORDER.
