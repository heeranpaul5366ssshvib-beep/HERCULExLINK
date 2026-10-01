# HERCULE-LM Frontier Readiness (measured, per-dimension)

- MODEL ARCHITECTURE: READY (own transformer, grad-verified).
- TRAINING SCALE: CPU small-scale proven (0.93M–100M instantiated;
  trained ≤ 3.1M). 100M+ training: BLOCKED here.
- DATA SCALE: pipeline proven to ~6.5k docs; sharded streaming
  implemented, multi-GB untested: PARTIAL.
- TRAINING QUALITY: small-scale loss/ppl measured; large-scale: N/A.
- INSTRUCTION QUALITY: mechanics proven (SFT smoke); quality: N/A.
- TOOL USE: synthetic format corpus built; model skill: NOT DEMONSTRATED.
- EVALUATION: N7 suite + framework path + honesty rules: READY.
- INFERENCE: greedy/temp/top-k/top-p, batched, score(); KV-cache
  NOT IMPLEMENTED; quantization NOT IMPLEMENTED (both declared).
- AGENT INTEGRATION: provider contract READY; Brain routing pending
  model capability (deliberately deferred).
- KNOWLEDGE DOCTRINE: retrieval-first — HERCULE memory/tools/
  verification answer facts; parameters are not required to
  memorize the internet. No whole-internet memorization attempted.
- SPLIT DOCTRINE: development = training stream samples; validation
  = hash-split docs; frozen = N7 eval set (never training input).
  Contamination gates enforced in code.
- CURVES: JSONL metrics log (`--metrics-log`) persists step/tokens/
  loss/valid/lr/gnorm/throughput/micro-index; never overwritten
  across runs (append per file).

No dimension is collapsed into a score. Nothing here claims
frontier competitiveness — that requires CUDA-scale evidence.
