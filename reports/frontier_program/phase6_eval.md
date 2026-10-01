# Phase 6 Evaluation (hercule-eval-v1) — MEASURED on CPU

## Harness validity

Reference-ceiling run scores **1.0 on every suite**: the harness,
verifiers, and scoring path are correct.

## Untrained nano baseline (honest zeros)

| Suite | Mean |
|---|---|
| MATH | 0.0 |
| STRUCTURED_OUTPUT | 0.0 |
| SAFETY | 0.0 |
| GENERAL | 1.0 (echo-containment probe, not understanding) |

Recorded in `baselines.json` as `hercule-lm-nano-untrained`. Any future
post-training claim must show a measured delta against this row
(improved/unchanged/regressed via `baselines.compare`).

## Suites available (13)

GENERAL, REASONING, MATH, CODING, TOOL_USE, RESEARCH,
STRUCTURED_OUTPUT, MULTILINGUAL, LONG_CONTEXT (to 4K probes;
model-ctx-gated, NOT-APPLICABLE beyond context is reported per run),
AGENT, SAFETY, RELIABILITY, ARC_STYLE (synthetic grids — explicitly
not ARC-AGI items/scores).

## GPU evaluation

NOT_RUN (0 GPUs). `gpu_auto_run.py::posttrain_hook` runs MATH /
STRUCTURED / SAFETY reference checks automatically on GPU boxes.
