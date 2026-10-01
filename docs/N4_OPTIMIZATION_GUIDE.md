# N4 Optimization Guide (what was tried, what holds)

1. Cache tokenized streams (`cached_stream`, hash-gated) — accepted.
2. Cache tokenizer training by dataset hash — accepted.
3. BLAS threads = physical cores via `HERCULE_LM_THREADS`/auto —
   accepted (+4% measured; never forced).
4. Benchmark harness with ckpt roundtrip verification — accepted.
5. `gc.disable()` — rejected (slower). Threads = logical — rejected.
6. Mixed precision, compile, kernel fusion, checkpointing,
   quantization — not applicable without torch; not faked.
7. Rule for future work: every optimization needs a correctness
   test (equivalence within dtype tolerance) and a measured
   before/after from `training/benchmark.py`. Anecdotal speedups
   are rejected.
