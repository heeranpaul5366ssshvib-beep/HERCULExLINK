# N5 Final Report — training portability & 100M readiness

- Objective/baseline: NumPy CPU pipeline (N3/N4); make it portable,
  resumable, estimable. No architecture change.
- Implementation: `device.py` (CPU/CUDA detection, explicit fail),
  checkpoint map-target + tokenizer/dataset compat validation,
  gradient accumulation + effective-batch manifests, standalone
  run/dataset manifests, `estimate.py`, registry origin fields.
- Files changed: `models/hercule_lm/{checkpoint,train}.py`
  (compat/accum/manifests only — no math changes).
- Files created: device/estimate modules, N5 tests, 5 N5 docs,
  this report.
- Tests: N3 17/17, N4 5/5, N5 21/26 (5 CUDA NOT_RUN skips),
  state-safety 11/11 → 54 passed, 5 skipped.
- Hardware: i3-3220 2C/4T, 8.5 GB RAM, no GPU. CUDA: UNAVAILABLE.
  GPU empirical testing: NOT AVAILABLE (abstraction tested on CPU).
- Dtype: fp32 actual everywhere; AMP: NOT AVAILABLE (declared).
- Checkpoint portability: IMPLEMENTED (format device-agnostic;
  CPU tested; GPU migration NOT empirically validated).
- Reproducibility: config/run/dataset identity chain complete.
- Estimators: labeled ESTIMATEs, math-verified in tests.
- 100M configuration: READY (frozen JSON + manifest chain).
- 100M training: NOT STARTED (N4 verdict stands).
- State isolation: hashes byte-identical across N5.
- Limitations: torch/CUDA/AMP/multi-GPU absent here by hardware,
  not by design gap; accumulation optimizer-step counting shifts
  LR schedule to step (optimizer-step) count — documented.
- Next step: N6 100M pretraining on CUDA-class hardware reusing
  this pipeline unchanged.
