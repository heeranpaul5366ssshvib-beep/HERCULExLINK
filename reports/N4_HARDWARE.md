# N4 Hardware (measured 2026-09-20)

- CPU: Intel i3-3220, 2 physical / 4 logical @ 3.3 GHz, x86-64.
  No AVX2 (Ivy Bridge) — modern PyTorch CPU wheels unusable; torch
  2.14 CPU wheel fails to import here. NumPy/BLAS is the compute path.
- RAM: 8.5 GB total, ~4.0 GB free at benchmark time.
- GPU: Intel HD Graphics (shared, no CUDA/ROCm/DirectML for training).
  GPU ACCELERATION: UNAVAILABLE (detected, not assumed).
- Disk: 39 GB free (checkpoints: micro 12 MB, 100M 1.03 GB).
- Python 3.14.6, NumPy 2.5.2, torch: none, CUDA: none.
- BLAS threads: physical cores (2) beat logical (4): 309.7 vs
  296.7 tok/s on micro (measured; `HERCULE_LM_THREADS` overrides).
