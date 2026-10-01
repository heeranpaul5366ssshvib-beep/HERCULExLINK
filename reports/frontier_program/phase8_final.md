# Phase 8 Final — GPU Execution + Capability + Moral Reasoning + Frontier Eval

**Status: CAPABILITY INFRA MEASURED — GPU BLOCKED (0 devices)**

## GPU / 100M / AMP / DDP / FSDP — BLOCKED/NOT_RUN

`gpu_auto_run.py` executes the full sequence on the first GPU box.
Nothing here substitutes CPU runs for GPU evidence.

## Measured capability gains (all on CPU, all honest)

- **Adaptive benchmarks**: tool-discovery + rule-discovery 0.0 → 1.0
  (`adaptive-better`); world-model rule confirmed, confidence 1.0
- **Coding agent**: baseline 0.0 → adaptive 1.0 on 3 planted-bug
  repair tasks with real pytest runs (attempts honestly cost more)
- **Research pipeline**: 0.5 grounding, 0 fabricated sources
- **Moral reasoning**: analyzer + 6-probe MORAL suite (ceiling 1.0);
  authorization stays in PolicyManager (widening blocked + tested).
  No consciousness/morality claims.
- **Long context**: 4K retrieval mechanics run (~40 s CPU, no OOM);
  capability ~0 untrained; beyond-ctx honestly NOT-APPLICABLE
- **Inference**: streaming matches batched; KV 1.6× on micro;
  padded batching NOT_IMPLEMENTED (documented reason)
- **Reasoning modes**: FAST fails / STANDARD validates /
  DEEP double-validates a 100-token task — capability per compute visible
- **Eval**: 14 suites, ceiling 1.0, frozen snapshot `bb82be72728b6ae5`

## Caught during Phase 8

CODING verifier tested reference code (model always passed) — fixed
to test candidate code, locked with a regression test.

## Tests — 179 passed, 0 failed, 9 skipped (4 CUDA NOT_RUN)

## Release

Scorecard (`scorecard_public.json`, no intelligence score) + updated
candidate checklist. Ships as an honest measured release.
