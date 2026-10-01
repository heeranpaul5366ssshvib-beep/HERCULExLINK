# N5 100M Configuration — READY (config), NOT STARTED (training)

Source: `models/hercule_lm/configs/hercule_lm_100m.json`
(hash-pinned; loading any other shape fails cleanly).

- vocab 16384 · hidden 640 · 16 layers · 10 heads · FFN 2560 ·
  context 512 · learned positions · LayerNorm · GELU · Xavier init.
- Parameters: 100,093,184 (computed, implementation-matched).
- Tokenizer: hercule-bpe-100m-v1 (own BPE; checksum-gated).
- Dataset: hercule-seed-v1 recipe (hash-gated streams).
- Memory (measured b2×256): peak RSS 3,998 MB vs ~4 GB free —
  fits marginally; larger batch/context is OOM territory.
- Throughput (measured): 16.7 tok/s → 2B-token budget ≈ 3.8 years.
- Optimizer/schedule: AdamW, cosine, clip 1.0 (same validated recipe).
- Status: 100M CONFIGURATION READY. 100M TRAINING: NOT STARTED
  (N4 verdict stands: NOT FEASIBLE ON CURRENT HARDWARE).
