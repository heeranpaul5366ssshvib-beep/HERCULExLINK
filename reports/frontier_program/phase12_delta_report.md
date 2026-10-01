# Phase 12 Delta Report

- Phase 11 → Phase 12 (micro-200 → micro-600 → s10m-200):
  held-out numeric **0/20 → 0/20 → 0/20: UNCHANGED**.
- Format adherence 20/20 sustained (no regression).
- Sequences 0/20 sustained.
- 100M-CUDA arm: NOT_RUN (tracked, not claimed).
- Milestone: NOT_ACHIEVED. Intervention unsuccessful at CPU-reachable
  scale — declared as such, no escalation to larger CPU models
  (s50m+ blocked by RAM anyway).
- Attribution: bottleneck is capacity + token volume, not duration
  (ruled out), not curriculum leakage (verified absent), not eval
  protocol (frozen, ceiling-validated).
