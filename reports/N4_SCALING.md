# N4 Scaling (measured, batch 4 unless noted)

| Model | Params | Seq | Step | Tok/s | Peak RSS | Ckpt bytes |
|---|---|---|---|---|---|---|
| nano | 933,120 | 32 | 0.33 s | 783.8 | 104 MB | — |
| micro | 3,088,384 | 64 | 1.75 s | 292.0 | 300 MB | ~36 MB |
| s10m | 10,561,024 | 64 | 2.92 s | 87.6 | 487 MB | 115 MB |
| s25m | 28,091,392 | 64 | 10.96 s | 46.7 | 1,472 MB | 303 MB |
| s50m | 52,662,272 | 64 | 18.34 s | 27.9 | 2,206 MB | 556 MB |
| 100m | 100,093,184 | 256/b2 | 30.65 s | 16.7 | 3,998 MB | 1,035 MB |

Throughput scales ≈ inversely with parameter count (compute-bound,
as expected on CPU BLAS). No configuration OOM'd; 100M peaks at
~4.0 GB against ~4.0 GB free — marginal, small batch only.
Per-size JSON records live in `training/benchmarks/`.
