# N8 Audit — training system as built (N3–N7)

Date: 2026-09-20. Source: direct inspection; no architecture changes.

- Model: NumPy decoder transformer; configs nano/micro/s10m/s25m/
  s50m/100m; gradcheck worst error 2.5e-06 (QKV per-head layout).
- Tokenizer: own byte-level BPE; micro tokenizer frozen for N8.
- Dataset: hercule-seed-v1 (hash c9eed266…), 6,450 paragraph docs,
  MIT-authored; frequency shaping = repetition in builders
  (facts ×40 shuffles, behaviors cycled ×100, stories 250 unique,
  arithmetic 3,000 unique).
- Checkpoints: npz + manifest + latest.json; strict arch/tokenizer/
  dataset validation; float32 moments (resume-bitwise).
- Training: AdamW, cosine-50-warmup, clip 1.0, accumulation,
  manifests, exit codes; ~300 tok/s (micro) on 2-core CPU.
- Evaluation: `evaluate.py` (loss/ppl/token-acc/arithmetic) +
  `training/n7/` suite (30 items) + framework integration path.
- State isolation: `training/` containment + `HERCULE_TEST_GUARD`;
  prod hashes verified per phase.
- Frozen N8 baseline: hercule-lm-micro-v0.1
  (`training/checkpoints/micro1/step_00000250`, valid 1.53,
  ppl 4.63, N7 1/30, arith 0/30) — read-only reference, never
  overwritten, never promoted-against.
- N8 changes (planned): new corpora B–E under `training/n8/`,
  experiment runner records, tests, docs. No model-code changes
  except where measurement proves necessity (none anticipated).
