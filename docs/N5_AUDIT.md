# N5 Audit — HERCULE-LM training system as built (N3+N4)

Date: 2026-09-20. Source: direct code inspection.

## 1-8. Current state

- Architecture: NumPy decoder transformer (`models/hercule_lm/model.py`),
  configs in `models/hercule_lm/configs/` (nano 0.93M / micro 3.09M /
  s10m / s25m / s50m / 100m = 100,093,184 params).
- Tokenizer: own byte-level BPE (`tokenizer.py`), checksum manifests.
- Data: hash splits, license/dupe gates, leakage check, seeded
  batches, stream cache (`data.py`).
- Loop: `train.py` (cosine, clip 1.0, atomic ckpts, Ctrl+C-safe,
  exit 0/2/3/130). No gradient accumulation yet (N5 adds it).
- Optimizer: AdamW + bias correction, decoupled decay (in `model.py`).
- Scheduler: cosine with 50-step warmup (in `train.py`).
- Checkpoints: npz weights + optimizer + manifest + `latest.json`
  (`checkpoint.py`). Format is device-agnostic NumPy arrays (no
  device tags) — portable by construction; N5 adds explicit
  map-target + compat validation.
- Resume: strict arch-hash check + step restore (tested).
- Device assumptions: CPU float32 everywhere, no device parameter.
- Threading: `threads.py` (`HERCULE_LM_THREADS`, physical-core auto).
- Batches: prebuilt list, seeded permutation, no accumulation.
- Gradients: full-materialized dict, global-norm clip.
- Validation: in-loop subset, configurable interval.
- Reproducibility: explicit seeds; determinism test passes.
- State isolation: `training/` only + `HERCULE_TEST_GUARD` in tests.
- Integration boundary: `HerculeLMProvider` (BaseAdapter contract);
  Brain routing pending further training.

## 9-16. Gaps N5 closes

Device abstraction (none) → `device.py`. Mixed precision (none) →
explicit fp32 reporting. Accumulation (none) → loop support.
Manifests (in-checkpoint only) → standalone run/dataset files.
Estimators (ad-hoc) → `estimate.py`. Registry (basic) → origin/
status fields. Multi-GPU (nothing) → honest single-device query +
PLANNED status.

## 17. Limitations carried forward

No torch/CUDA on this machine: GPU, AMP, and multi-GPU items are
IMPLEMENTED-as-abstraction + HARDWARE VALIDATION NOT AVAILABLE,
never fake passes. 100M training remains NOT FEASIBLE here.

## 18-19. Change list / non-changes

N5 changes: new `device.py`, `estimate.py`; checkpoint compat
fields; accumulation + manifests in `train.py`; tests; docs.
N5 will NOT change: model math, tokenizer algorithm, loss,
optimizer semantics, Brain/planners/policy/verification, defaults.
