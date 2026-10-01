# N3 Architecture — HERCULE-LM

Date: 2026-09-20.

## Layout

- `models/hercule_lm/config.py` — explicit configs + exact param count.
- `models/hercule_lm/tokenizer.py` — own byte-level BPE (train/encode/decode/save/load).
- `models/hercule_lm/model.py` — NumPy transformer (forward + hand-written
  backward, AdamW, clipping, greedy/temperature generation).
- `models/hercule_lm/checkpoint.py` — atomic npz + manifest + `latest.json`.
- `models/hercule_lm/data.py` — sources, validation gate, hash splits,
  leakage check, manifests, batching.
- `models/hercule_lm/train.py` / `generate.py` / `evaluate.py` — CLIs.
- `models/hercule_lm/provider.py` — `BaseAdapter` contract implementation.
- `training/` — corpus builders, CLI shims, `data/`, `tokenizer/`,
  `checkpoints/`, `prepare_data.py`.
- `models/registry.json` — versioned model entries (EXPERIMENTAL).

## Gradient proof

Float64 finite-difference gradcheck over every parameter family
(QKV/biases, output proj, FFN, norms, embeddings, head): worst
relative error 2.5e-06. The one real bug found this way (QKV layout
must be per-head [Qh Kh Vh], matching the forward reshape) is fixed
and covered by `test_backward_gradcheck_float64`.

## Non-goals honored

No pretrained weights, no LoRA, no `transformers`/`torch` usage, no
production architecture changes (all N3 code is new files; the only
production touchpoints are the additive provider registration path
used by tests and the evaluation trace, both pre-existing seams).
