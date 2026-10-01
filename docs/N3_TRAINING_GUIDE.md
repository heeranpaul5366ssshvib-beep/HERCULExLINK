# N3 Training Guide

## Commands

```text
python training/build_corpus.py
python -m training.prepare_data
python -m training.train --config hercule_lm_nano --steps 200
python -m training.train --resume training/checkpoints/<run>/step_00000200
python -m training.generate --checkpoint <dir> --prompt "Q: Calculate 317 + 542."
python -m training.evaluate --checkpoint <dir> --arithmetic-n 50
```

## Exit codes

0 ok · 2 config/data/checkpoint problem (NO_DATASET, INVALID_DATASET,
MODEL_CONFIG_INVALID, CHECKPOINT_MISMATCH/CORRUPTED, DATASET LEAKAGE)
· 3 resource/divergence (OUT_OF_MEMORY, TRAINING_DIVERGED) · 130 Ctrl+C
(interrupted cleanly after saving).

## Budgets (measured, 2-core CPU)

- nano (0.93M): ~800 tok/s → 120 steps ≈ 1 min.
- micro (3.09M): ~300 tok/s → 291 steps ≈ 9 min.
- 100M: ≈ 10 tok/s projected → full pretraining BLOCKED here.

## State

Checkpoints under `training/checkpoints/` (never `data/`). Production
guard (`HERCULE_TEST_GUARD`) applies to test runs; training writes
only inside `training/`.
