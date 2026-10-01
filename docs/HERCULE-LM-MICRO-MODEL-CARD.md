# HERCULE-LM-MICRO Model Card (TRAINED, EXPERIMENTAL)

- Architecture: own NumPy decoder transformer (learned positions,
  LayerNorm, causal MHA, GELU FFN): vocab 1024, hidden 192, 6 layers,
  6 heads, FFN 768, ctx 128. **3,088,384 params** (computed).
- Tokenizer: hercule-bpe-micro-v1 (own BPE, checksum-gated).
- Data: hercule-seed-v1 (MIT-authored, hash c9eed266…).
- Training: 291 steps / 148,544 tokens, AdamW 3e-4 cosine, batch
  8×64, fp32 CPU (~9 min). Valid 1.53 / ppl 4.63 / token-acc (record).
- Evaluation: N7 1/30 vs random 0/30; held-out arithmetic 0/30.
- Checkpoint: `training/checkpoints/micro1/step_00000250` (+manifest).
- Limitations: answer shapes before arithmetic; tiny capacity; CPU-only.
- Intended use: from-scratch LM research. Non-use: production,
  safety-critical, ChatGPT replacement.
- Known failures: repetitive loops; must never bypass HERCULE
  verification (which remains authoritative).
