# HERCULE-LM-100M Model Card — STATUS: NOT TRAINED (N6 BLOCKED)

This card describes the FROZEN CONFIGURATION, not a finished model.
No 100M checkpoint exists. Do not present this card as a trained
model release.

- Name: HERCULE-LM-100M (config v1, `hercule_lm_100m`).
- Architecture: causal decoder transformer (own NumPy code):
  vocab 16384, hidden 640, 16 layers, 10 heads, FFN 2560, ctx 512,
  learned positions, LayerNorm, GELU, Xavier init. 100,093,184 params.
- Tokenizer: hercule-bpe-100m-v1 (own BPE, checksum 843534c8f576ecde).
- Training data: hercule-seed-v1 (MIT-authored; hash c9eed266…).
- Objective: causal LM. Optimizer AdamW, cosine, batch 2×8=16, fp32.
- Hardware: requires CUDA-class machine (current: none) — BLOCKED.
- Validation: N/A (never trained). Random init proof: recorded.
- Limitations: does not exist as weights; small siblings learn
  answer shapes before arithmetic (0/30 at micro scale).
- Intended use: pretraining target for N6 on suitable hardware.
- Non-intended use: everything requiring a working model.
- Weights origin: N/A (random initialization procedure documented).
- Pretraining status: NOT STARTED. Instruction-tuning status: N/A.
