# N5 Device Architecture

- `models/hercule_lm/device.py`: `describe_backend()` (probed, never
  claimed), `get_training_device(auto|cpu|cuda[:N])`,
  `move_batch_to_device` (explicit CPU no-op), `topology()`
  (world_size 1, distributed PLANNED).
- Backends: `numpy` (reference, always) and `torch` (optional; used
  only when importable AND CUDA probed). No torch installs performed.
- Requested-but-unavailable CUDA fails clearly; no silent fallback.
- Mixed precision: requested vs actual always reported; NumPy path
  is fp32-only (honest, not forced). AMP: NOT AVAILABLE here.
- Multi-GPU: single-device only; no fake distribution.
