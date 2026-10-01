# Evaluation, Experience, Traces

## Evaluation (`evaluation/`)

- `failures.py`: 12-category taxonomy (INPUT … INTERNAL) with
  retryable/fatal severity, `classify_failure` for legacy free-text
  errors, and `FailureLedger` aggregating recurrences + recovery rate.
  Classify → determine recovery → execute → evaluate, using aggregates.
- `metrics.py`: `TaskQuality` (completion + verification + error rate +
  efficiency + feedback) keeps every dimension beside the weighted
  score; `compute_task_quality` distills TaskManager dicts read-only.
  `SubsystemScore`/`aggregate_scores` never hide breakdowns.
- `benchmarks.py`: category registry (reasoning, planning,
  tool-selection, memory/knowledge retrieval, model routing, task
  completion, failure recovery) with deterministic hermetic cases,
  history, and JSON export for regression tracking.
- `engine.py`: `EvaluationEngine` (per-subsystem scorers, run history,
  export) + `build_baseline` performance suite (context, retrieval,
  routing, planning, tool, end-to-end timings recorded pre-optimization).

## Experience (`cognition/experience/`)

`ExperienceManager.record_from_task` distills goal type, strategy,
tools, outcome, failures, recovery, verification, retries — no raw
logs. `propose_procedure` requires ≥3 supporting experiences at
≥0.8 mean success; `validate_procedure` gates promotion explicitly.

## Traces (`system/observability/trace.py`)

`RequestTrace` spans request → context → retrieval → model_selection →
reasoning → planning → decisions → tools → agents → verification →
final_result, keyed by correlation/request/task/execution/agent ids.
`Tracer` optionally mirrors into `ObservabilityManager`. The five
`explain_*` helpers answer why-model/memory/tool/retry/verification
from recorded metadata only.
