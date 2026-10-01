# HERCULE-LM-100M — Model Card (EXPERIMENTAL, untrained at this scale)

Version: config v1 (no 100M checkpoint exists — see limitations).

- Architecture: causal decoder transformer (HERCULE-authored NumPy):
  learned absolute positions, pre-norm LayerNorm blocks, causal MHA,
  GELU FFN, residual connections, output projection.
- Configuration (`models/hercule_lm/configs/hercule_lm_100m.json`):
  vocab 16384, hidden 640, 16 layers, 10 heads, FFN 2560, context 512,
  Xavier-uniform init, seed-controlled. **Parameter count: 100,093,184**
  (computed, matches implementation layout exactly).
- Tokenizer: own byte-level BPE (`hercule-bpe-100m-v1`, 16384).
- Training data: `hercule-seed-v1` (HERCULE-authored/synthetic, MIT).
- Initialization: random (Xavier-uniform); no pretrained weights anywhere.
- Hardware used: none at 100M scale (see below).
- Training duration: N/A — **pretraining BLOCKED, insufficient compute**
  (2-core CPU ≈ 10 tok/s projected at 100M; ~1B tokens ≈ 3 years).
- Proven smaller siblings: nano (0.93M, trained, ppl 14.4),
  micro (3.09M, trained 291 steps, valid loss 1.53 / ppl 4.6,
  random control ppl 1219.6).
- Limitations: 100M config defined/validated but never trained;
  small models learn answer shapes before arithmetic; NumPy CPU only.
- Intended use: research into from-scratch HERCULE models.
- Non-intended use: production reasoning, safety-critical decisions.
- Known failures: small checkpoints repeat frequent tokens; 0/30
  held-out arithmetic exact-match at micro scale.
- Checksum: config hash recorded per checkpoint manifest at train time.
