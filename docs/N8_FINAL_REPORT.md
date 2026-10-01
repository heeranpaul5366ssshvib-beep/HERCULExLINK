# N8 Final Report — corpus growth + frequency-shaping ablation

N8 STATUS: PASS (valid experiments, honest mixed results).

- Hardware/backend: i3-3220 2C/4T, NumPy CPU fp32, no GPU.
- Baseline frozen: micro1 (hash-verified in tests, never touched).
- Corpora: seed_unique / controlled_2x / expanded / arithmetic
  (+manifests, +contamination clean, +quality reports).
- 5/5 experiments completed at fixed budget (150 steps); none
  deleted, none promoted.
- Validation/evaluation/regression/generation/checkpoint/resume:
  all executed, records in `training/n8/`.
- State isolation: guard active; production hashes verified below.
- Tests: N3 17 + N4 5 + N5 21 + N6 10 + N7 13 + N8 12 + state 11
  (see regression run for exact totals).
- 100M: CONFIGURED / NOT TRAINED (unchanged).
- Conclusions: dedup ≥ repetition; expansion helps slightly;
  exact-2x adds nothing; arithmetic-heavy narrows generality
  without teaching arithmetic at this scale. All small-sample;
  none promoted.
- Next: N9 — longer-budget confirmation of C vs B on a stronger
  machine, or architecture/data levers from N8 evidence.
