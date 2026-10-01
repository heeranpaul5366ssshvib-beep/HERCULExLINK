# N4 Optimization ledger

## Accepted

1. Tokenized-stream cache (`cached_stream`, hash = corpus +
   tokenizer checksum + seq + format v1). Reason: kill repeat BPE +
   encode per invocation. Baseline: 8.5 s retrain + 0.25 s encode.
   Optimized: cache-hit load (~ms scale; byte-identical, tested).
   Memory change: none at train time. Correctness: equivalence +
   invalidation tests pass.
2. Tokenizer-train cache (dataset-hash file; retrain only on corpus
   change). Same class of saving (8.5–19.8 s on repeat runs).
3. BLAS thread helper (`HERCULE_LM_THREADS`, physical-core auto).
   Baseline 296.7 → 309.7 tok/s (+4.4%, measured). No semantic
   content: env plumbing only.
4. Benchmark harness itself (visibility, ckpt timing, roundtrip
   verification) — enables all future measurement.

## Rejected / not applicable

- `gc.disable()`: slower (1.70 → 2.03 s/step). REJECTED.
- Threads = logical count: slower than physical. REJECTED.
- Mixed precision / autocast / grad scaling: no torch — NOT
  APPLICABLE (not forced, not faked).
- `torch.compile` / SDPA / optimized attention kernels: no torch —
  NOT APPLICABLE. NumPy attention kept as the reference
  implementation (it IS the debugged implementation).
- Activation/gradient checkpointing: NOT IMPLEMENTED — memory fits
  every size through 100M at small batch; recompute would cost
  ~30% speed for no solved limitation.
- Quantized training: NOT IMPLEMENTED (correctness first, per spec).

## Correctness verification

No model-semantics change shipped in N4 (plumbing + caches only).
Same-seed determinism test passes; float64 gradcheck suite passes
unchanged; quality check: micro valid loss 1.53 / ppl 4.63 and
arithmetic 0/30 re-measured identical post-change.
