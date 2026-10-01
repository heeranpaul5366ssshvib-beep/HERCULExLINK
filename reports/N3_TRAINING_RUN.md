# N3 Training Run — micro1 (STATUS: completed small-scale run)

- Model: hercule-lm-micro, 3,088,384 params, seed 0.
- Dataset: hercule-seed-v1 (6,450 docs; hash in manifest).
- Tokenizer: hercule-bpe-micro-v1 (own BPE).
- Config: batch 8, seq 64, lr 3e-4 cosine, clip 1.0, AdamW.
- Budget: 291 steps / 148,544 tokens in ~9 min (~300 tok/s), then
  time-box stopped (checkpointed cleanly).
- Train loss: ~6.6 → 0.63–1.5 band. Valid: 1.7072 (in-run) / 1.532
  (post-hoc full eval), perplexity 4.63.
- Checkpoint: `training/checkpoints/micro1/step_00000250`
  (+ optimizer state, manifest, run record).

## 100M pretraining

STATUS: **BLOCKED — INSUFFICIENT COMPUTE**. Projected ≈ 10 tok/s
on this CPU; meaningful token budgets imply years. Config,
tokenizer recipe, and pipeline are ready; execution requires a
stronger machine. No fake checkpoint was created.
