# HERCULE-LM Master Final Report

- Current model: hercule-lm-micro-v0.1 (3,088,384 params, TRAINED/
  EXPERIMENTAL); nano TRAINED; s10m–7B CONFIGURED (counts computed);
  100M CONFIGURED/NOT TRAINED.
- Tokenizer: own BPE, frozen per config, checksummed.
- Corpus: hercule-seed-v1 + instruct/tool/code sets, MIT-authored.
- Training status: small-scale CPU proven (nano/micro/N8/SFT smokes).
- Hardware: i3-3220 CPU, NumPy fp32; CUDA/AMP/multi-GPU absent.
- Backend: NumPy reference; torch paths declared NOT AVAILABLE.
- Actual training performed: listed runs only (micro1 291 steps,
  N8 A–E 150 steps each, smokes); no 100M training.
- Actual evaluation: N7 1/30 vs random 0/30; arith 0/30 (honest);
  UAI control plane 64/64 mock (separate system, unaffected).
- Instruction/tool-use: mechanics + corpora READY; quality N/A.
- Inference: greedy/temp/top-k/top-p, batched, score(); no KV-cache,
  no quantization (declared).
- HERCULE integration: provider contract tested; routing deferred.
- Benchmarks: scaling table measured to 100M; no frontier claims.
- Limitations: §Known limitations in every card; single-seed
  ablations; CPU-only throughput.
- Blocked: 100M+ training, CUDA execution, AMP, distributed,
  frontier-competitiveness evidence.
- Next hardware requirement: CUDA-class GPU (class only).
- Traceability: every number resolves to a manifest, eval JSON,
  benchmark JSON, test assertion, or a NOT MEASURED/BLOCKED label.
