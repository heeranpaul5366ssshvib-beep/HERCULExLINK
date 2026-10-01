# HERCULE-LM Backends: NumPy Reference + Torch (CPU/CUDA)

HERCULE-LM has two training backends for the **same architecture**
(token embedding + learned positions, N pre-norm transformer blocks
with causal multi-head attention and tanh-GELU FFN, final LayerNorm,
LM head, mean cross-entropy, Xavier-uniform random init, no
pretrained weights anywhere):

| Backend | Module | Device | Role |
|---|---|---|---|
| NumPy reference | `models/hercule_lm/model.py` | CPU | correctness, deterministic tests, historical regression |
| Torch | `models/hercule_lm/torch_model.py` + `train_torch.py` | CPU and CUDA | real training, GPU execution |

QKV layout (both backends): one packed `qkvW [hidden, 3*hidden]`
reshaped to `[B,T,heads,3*head_dim]` and split per head into
`[Qh,Kh,Vh]`. Torch parameter names live under `blocks.<i>.<name>`
(`nn.Module` forbids `.` in registered names);
`numpy_param_dict()` / `load_numpy_param_dict()` translate to the
NumPy `L<i>.<name>` names. The architecture hash comes from the
shared `HerculeLMConfig`, so it is identical across backends.

## Selecting a backend

`python -m models.hercule_lm.train` (and `python -m training.run`,
which forwards `--device/--backend/--dtype/--amp`):

- `--device cpu` → NumPy reference (default).
- `--device cuda` / `cuda:N` → Torch on CUDA. Fails clearly
  (`DEVICE_UNAVAILABLE`, exit 2) when CUDA is missing. **Never falls
  back to CPU silently.**
- `--device auto` → Torch+CUDA when probed, else NumPy CPU.
- `--backend torch --device cpu` → Torch on CPU (parity/benchmark use).
- `--backend numpy --device cuda` → rejected (NumPy is CPU-only).

## CUDA requirements

- A CUDA-enabled PyTorch build (`torch.cuda.is_available() == True`)
  plus a visible GPU. This repo's dev box has a CPU-only torch, so
  CUDA paths are honest `NOT_RUN` skips here — see the report for how
  to validate on a GPU machine.
- FP32 first: compute is FP32 unless `--amp` is given.
- `--amp bf16` runs on CUDA (and CPU); `--amp fp16` requires CUDA
  (rejected clearly on CPU). AMP is recorded in the manifest; no
  speedup is claimed until measured.

## Exact commands

```bash
# NumPy CPU (reference)
python -m training.run --config models/hercule_lm/configs/hercule_lm_micro.json --device cpu --steps 10

# Torch CUDA (real GPU training)
python -m training.run --config models/hercule_lm/configs/hercule_lm_micro.json --device cuda --steps 10

# CUDA dry-run (gate only, no training)
python -m training.run --config models/hercule_lm/configs/hercule_lm_100m.json --device cuda --steps 10 --dry-run

# Direct trainer smoke (torch CPU on this box)
python -m models.hercule_lm.train --config hercule_lm_nano --backend torch --device cpu --steps 10

# Resume a torch run
python -m models.hercule_lm.train --config <cfg> --backend torch --device cuda \
  --resume training/checkpoints/<run>/step_<N> --steps <M>
```

`--steps N` is a **bounded benchmark**, not proof that full
pretraining is practical; full runs still go through the hardware
timeline-feasibility gate.

## Checkpoint formats

- NumPy: `weights.npz + manifest.json`,
  `checkpoint_format="hercule-npz-v1"`. Unchanged and loadable.
- Torch: `weights.pt` (model + optimizer + torch RNG) **plus**
  `weights.npz` (params-only export) + `manifest.json` with
  `checkpoint_format="hercule-torch-v1"`, `backend="torch"`,
  `device/dtype/amp`, architecture hash, tokenizer checksum, dataset
  hash, random-init origin.
- Resume validates architecture/tokenizer/dataset identity and
  rejects mismatches (`CHECKPOINT_MISMATCH`, `TOKENIZER_MISMATCH`,
  `DATASET_HASH_MISMATCH`).
- `map_to` is explicit: `cpu` always works; `cuda*` needs CUDA and a
  torch model (the NumPy model is CPU-only and fails clearly).
  Cross-backend resume (NumPy `.npz` → torch) is an explicit
  conversion with a fresh optimizer.

## CPU vs CUDA differences

- Initialization is bit-identical across backends for the same seed
  (same NumPy RNG draw order); CPU training trajectories reproduce
  under fixed seed+order (verified: resumed step-40 loss exactly
  equals the uninterrupted run).
- CUDA trajectories are **not** claimed bit-identical to CPU
  (parallel reduction order, cuDNN kernels). Parity tolerances:
  forward logits rtol=1e-4/atol=1e-5, loss abs<1e-4, grads
  rtol=1e-4/atol=1e-6, one AdamW step rtol=1e-2/**atol=1e-4**.
- The looser optimizer-step tolerance is principled: Adam divides by
  `|g|`, so coordinates whose true gradient cancels to ~0 take
  different tiny steps while agreeing in absolute terms (worst
  observed absolute drift after one lr=1e-3 step: ~4e-5, confined to
  near-zero updates).

## Deterministic guarantees and limitations

- Same seed + same backend + same device + same batch order →
  reproducible (torch seeded: `manual_seed`, `cuda.manual_seed_all`,
  cuDNN deterministic, NumPy/Python seeded).
- Across backends/devices: close within the tolerances above, never
  bit-identical — and never claimed so.
- Data pipeline (tokenizer, cached streams, manifests, splits,
  leakage/licensing checks) is shared, not rewritten; batches convert
  NumPy→torch once per micro-batch.

## Multi-GPU status

Single-device by default. DDP infrastructure is implemented
(`models/hercule_lm/distributed.py`, launcher `scripts/ddp_launch.py`):

```bash
# 2-GPU (on a 2-GPU box; NOT validated — 0 GPUs here)
python scripts/ddp_launch.py --nproc 2 -- \
  -m models.hercule_lm.train --config hercule_lm_nano \
  --backend torch --device cuda --steps 100
```

A 2-process CPU/gloo harness run passes (proves plumbing, gradient
sync, rank-0 checkpointing) but is **not** multi-GPU proof.
`distributed_status` reports `NOT_IMPLEMENTED` single-device,
`DDP <backend> world_size=N` in distributed runs. FSDP scaffold
(`models/hercule_lm/fsdp.py`) refuses single-process wrapping.
Multi-GPU is claimed only after a real ≥ 2-CUDA-device run.

## Measured throughput (this box: 4-core CPU, no GPU)

Same dataset/seq/batch/steps, FP32, `--steps 10`, batch 8:

| Config | NumPy CPU | Torch CPU | Torch CUDA |
|---|---|---|---|
| hercule-lm-micro | ~260–385 tok/s | ~550–970 tok/s | NOT_RUN (no GPU) |
| hercule-lm-s10m | ~62–64 tok/s | ~182–198 tok/s | NOT_RUN (no GPU) |

Loss trajectories are identical across backends
(micro: 7.0252→5.6014; s10m: 7.4527→5.6920). Historical estimate
table in `training/run.py` (`_known_throughput`) is stale
estimation, not measurement — do not mix the two.

## Environment note (2026-09-23)

The repo `.venv` shipped a corrupted torch install (version metadata
`None`, missing `torch.nn`). It was repaired with a clean
`torch-2.14.0+cpu` wheel install; no project code depends on the
corruption. On a GPU box, install a CUDA torch build instead — no
code changes needed.
