# N4 Audit — HERCULE-LM training system as built (N3)

Date: 2026-09-20. Source: direct code inspection.

## Implementation under test

- `models/hercule_lm/model.py` — NumPy decoder transformer. Forward
  caches every intermediate; `loss_and_backward` hand-writes all
  gradients (gradcheck worst error 2.5e-06, float64). AdamW with bias
  correction + decoupled decay; global-norm clipping. float32
  throughout; no autocast/mixed precision (no torch installed).
- `models/hercule_lm/train.py` — cosine schedule (50-step warmup),
  atomic checkpoints + `latest.json`, Ctrl+C-safe, exit codes
  0/2/3/130. Batches rebuilt per step from a pre-tokenized stream;
  tokenizer retrained from corpus on every invocation (no cache).
- `models/hercule_lm/data.py` — hash splits, license/dupe/encoding
  gates, leakage check, sliding-window batching (seeded permutation).
- `models/hercule_lm/tokenizer.py` — pure-Python byte-level BPE.
- `models/hercule_lm/checkpoint.py` — npz + manifest, tmp+replace.
- Dataloader: in-memory token stream, no workers, no mmap, no cache.
- Device/dtype: CPU float32 only. No torch, no CUDA, no DirectML, no
  `torch.compile`, no SDPA, no checkpointing-of-activations.
- Validation: full valid batches (≤8) every N steps, in-loop.
- Logging: stdout lines only. Seeding: explicit everywhere.

## Files reused / not duplicated

Numpy (already a dependency), `system/state_guard.py`, existing
test conventions. Nothing in `brain/`, planners, or providers is
touched by N4 unless measurement proves it necessary.

## Cartography for §5 profiling

Stages: corpus load → BPE train → encode stream → batch build →
forward → loss → backward → clip → AdamW → (eval) → (checkpoint).
Timers to add around each; memory via Win32 API (stdlib ctypes —
no psutil dependency).
