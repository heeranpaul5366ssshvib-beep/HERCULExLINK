# N6 Pretraining Audit

- Model: `hercule_lm_100m` — decoder transformer, 100,093,184 params
  (hash `2de3e5574a3bb715`), Xavier-uniform seed 20260613, finite ✓.
- Tokenizer: `hercule-bpe-100m-v1`, 3,736 realized / 16,384 slots,
  checksum `843534c8f576ecde`, round-trip verified.
- Dataset: `hercule-seed-v1`, hash
  `c9eed266…f7574`, 6,450 docs (5,960/163/327), all MIT-authored.
- Config: batch micro 2 × accum 8 = 16 effective, seq 256, AdamW
  lr 3e-4 cosine, clip 1.0, fp32 CPU, 2B-token Chinchilla budget.
- Objective: causal LM, verified masking (N3 causality test).
- Checkpoint/resume/validation/rng/state-isolation: N5 mechanisms.
- Hardware gate: BLOCKED (no CUDA, RAM floor, 1,386-day timeline).
- Run status: never started. No training occurred; nothing to report
  beyond readiness artifacts (`training/n6/`).
