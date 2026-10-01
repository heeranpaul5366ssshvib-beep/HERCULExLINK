# N7 Audit — repository state for evaluation/readiness

Date: 2026-09-20. Source: direct inspection.

## Model configurations (measured counts)

- nano 933,120 — TRAINED (smoke1, 160 steps, valid 2.67).
- micro 3,088,384 — TRAINED (micro1, 291 steps, valid 1.53/ppl 4.63).
- s10m/s25m/s50m — CONFIGURED, benchmarked, NOT TRAINED.
- 100m 100,093,184 — CONFIGURED, NOT TRAINED (N6 BLOCKED).

## Tokenizer / dataset / checkpoints

- Own byte-level BPE; micro tokenizer in `training/tokenizer/`;
  100M tokenizer frozen (checksum 843534c8f576ecde).
- Corpus `hercule-seed-v1`, hash c9eed266…, 6,450 docs, MIT-authored.
- Checkpoints: `training/checkpoints/{smoke1,micro1,overfit1,
  randomctl}` + manifests + `latest.json` where written.

## Code

- Training loop, AdamW, cosine, accumulation, manifests, device
  abstraction (NumPy CPU; torch/CUDA paths honestly absent),
  estimators, benchmark harness, provider adapter, eval CLI
  (loss/ppl/arithmetic), framework integration tests.
- Reproducibility: seeds, hash splits, determinism tests.
- State isolation: `training/` containment + `HERCULE_TEST_GUARD`.

## Limitations carried into N7

- Small models learn answer shapes before arithmetic (0/30).
- No GPU/AMP/multi-GPU on this machine (declared, not faked).
- 100M training blocked; N7 must not start it.
