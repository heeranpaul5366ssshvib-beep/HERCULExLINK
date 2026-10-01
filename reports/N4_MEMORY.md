# N4 Memory analysis (100M, fp32, AdamW)

## Theoretical floor (exact, from the parameter layout)

- Parameters: 100.09M × 4 B = 400 MB.
- Gradients: 400 MB.
- AdamW state (m + v): 800 MB.
- Subtotal, weights-derived: **1,600 MB** (checkpoint file at
  1,035 MB is consistent: compressed params + optimizer state).

## Measured (b2 × seq256, peak RSS 3,998 MB)

- Activations + caches + transient copies + Python/BLAS overhead:
  ≈ 2,400 MB above the weights-derived floor at this batch/seq.
- Scaling anchor points (peak RSS): 3M → 300 MB, 10M → 487 MB,
  28M → 1,472 MB, 53M → 2,206 MB, 100M → 3,998 MB.

## Reading

Memory FITS at batch ≤ 2 / seq ≤ 256, with ~0 MB headroom against
4 GB free — any OS fluctuation, larger batch, or longer context
risks OOM. Mixed precision is unavailable (no torch); activation
checkpointing was evaluated and rejected (unneeded at small scale,
~30% slower, does not fix the time bound below).
