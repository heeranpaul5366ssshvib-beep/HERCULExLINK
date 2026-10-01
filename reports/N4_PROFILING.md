# N4 Profiling

Method: `python -m training.benchmark` (component timers, Win32 peak
RSS via stdlib ctypes, checkpoint save/load cycle with roundtrip
verification). No permanent slowdown: timers live only in the
benchmark entry point, not in `train.py`.

## Findings

- Forward 29–37% / backward 46–58% / optimizer+clip 3–5% across
  sizes: textbook matmul-bound profile on CPU BLAS.
- `gc.disable()` during the loop: REJECTED (2.03 vs 1.70 s/step).
- Threads: 2 (physical) > 4 (logical) by ~4%.
- Tokenizer retrain dominated short-run wall time (8.5 s micro,
  19.8 s s10m) → cached (hash-gated).
- Checkpoint micro: ~12 MB-scale files, seconds to write; 100M:
  1,035 MB, tens of seconds (measured in benchmark record).
- Thermal: micro throughput stable across N3 run (~300) and N4
  reruns (~292); no throttling signal observed on short/medium runs.
  Long-run throttling: NOT MEASURED (no multi-hour run performed).
