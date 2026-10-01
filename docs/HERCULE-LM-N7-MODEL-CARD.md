# HERCULE-LM N7 Model Card

## Trained small models (ACTUAL)

**hercule-lm-micro-v0.1** — 3,088,384 params, own BPE (1,024),
hercule-seed-v1, 291 steps / 148,544 tokens, AdamW cosine,
valid loss 1.532 / ppl 4.63 / next-token acc (see eval record),
held-out arithmetic 0/30, N7 eval 1/30 (ctx-00 recall) vs random
0/30. Status: TRAINED/EXPERIMENTAL. Checkpoint:
`training/checkpoints/micro1/step_00000250`.

**hercule-lm-nano-v0.1** — 933,120 params, smoke-trained 160 steps,
valid 2.67. Status: TRAINED/EXPERIMENTAL.

## Configured, NOT TRAINED

**hercule-lm-100m-v0.0** — 100,093,184 params. Status: CONFIGURED.
Training: BLOCKED (N6 gate). No weights exist.

## Common

- Architecture: own NumPy decoder transformer (learned positions,
  LayerNorm, causal MHA, GELU FFN). Tokenizer: own byte-level BPE.
- Initialization: Xavier-uniform random; no pretrained weights
  anywhere (lineage-enforced in code).
- Data license: HERCULE-authored (MIT, repo).
- Hardware: 2-core CPU, NumPy; GPU UNAVAILABLE.
- Reproducibility: seeds + hashes + manifests recorded.
- Limitations: small models emit answer shapes before arithmetic;
  0/30 held-out arithmetic at micro scale; not instruction-tuned;
  not a general reasoner.
- Intended use: from-scratch LM research inside HERCULE.
- Non-goals: production reasoning, safety-critical use, ChatGPT
  replacement.
- Known failures: repetitive-token loops on unfamiliar prompts;
  fabricated-looking completions must never be trusted without
  HERCULE verification (which remains authoritative).
