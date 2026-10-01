# Frontier Master Audit (P0) — what exists vs what the program needs

Date: 2026-09-20. Method: code inspection. Verdicts: PRESENT /
PARTIAL / MISSING (with N-phase to address or honest BLOCKED).

## Present and frozen (do not rewrite)

- NumPy decoder transformer + hand-verified backward (gradcheck
  2.5e-06), AdamW, cosine, clip, accumulation, manifests.
- Own BPE tokenizer + checksums; hash-split data pipeline with
  license/dupe/leakage gates; stream cache.
- Atomic checkpoints + strict lineage (arch/tokenizer/dataset) +
  resume-bitwise tests; device abstraction (CPU real, CUDA honest).
- Estimates (memory/time, labeled), benchmark harness, scaling
  table 0.93M→100M (all measured), provider adapter, eval CLI +
  N7 suite + framework path, state guard, registry (basic).

## Gaps closed by this program (new, small, tested)

- P1: 300M/1B/3B/7B CONFIGS (computed counts only, no training).
- P4: tokenizer fertility/compression/code/number metrics.
- P5/P6: near-dedup (shingle Jaccard) + quality dimensions.
- P7: sharded streaming loader with resumable cursor.
- P9/P10/P14: RNG capture, dataloader cursor + scheduler params in
  checkpoints, JSONL metrics log.
- P17–P20: instruction/tool/coding corpora (authored) + SFT mask
  mode + syntax-check eval (no execution of model output).
- P23: context-length memory/quality probes (short/medium/long).
- P27: batched generation, top-k/top-p sampling, provider score().
- P28/P29: adapter score(), registry lifecycle states.
- P30: micro + 100M-config cards.
- P33/P36/P37: any-config hardware gate + `training/run.py`
  orchestrator with dry-run.
- P35/P38: research-log convention + readiness doc.

## Honestly absent (hardware or scope, declared not faked)

- CUDA/AMP/multi-GPU execution, KV-cache, quantization, TorchScript/
  ONNX/GGUF export, cloud/distributed training, web-scale corpus.
- 100M+ training (BLOCKED on this CPU), instruction-tuned quality,
  frontier competitiveness (not claimed anywhere).
