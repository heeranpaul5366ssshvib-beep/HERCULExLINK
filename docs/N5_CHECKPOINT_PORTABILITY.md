# N5 Checkpoint Portability

- Format unchanged (npz + manifest + latest.json): NumPy arrays
  carry no device tags, so CPU↔CUDA migration is a load-time
  placement decision via `load_checkpoint(..., map_to=...)`.
- `map_to="cpu"` always works; `cuda*` without torch/CUDA raises
  CHECKPOINT_MAP_FAILED (tested). Torch-device mapping: PLANNED.
- Compatibility is validated, not assumed: architecture hash
  (pre-existing), tokenizer checksum (N5), dataset hash (N5) —
  mismatches raise TOKENIZER_MISMATCH / DATASET_HASH_MISMATCH.
- Optimizer + scaler slots persist; RNG metadata recorded
  (seed, streams, numpy version).
- GPU empirical validation: NOT AVAILABLE (no CUDA hardware).
  Mechanism implemented; CPU↔CPU migration tested.
