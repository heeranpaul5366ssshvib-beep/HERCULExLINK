# HERCULE-LM Kaggle GPU Training Pipeline

Local PC orchestrates; Kaggle GPU trains. Never the reverse.

## Setup (once)

1. `pip install kaggle` (already in `.venv`)
2. Kaggle Settings → Account → API → Create New Token, then either:
   - set `KAGGLE_USERNAME` + `KAGGLE_KEY` env vars, or
   - place `kaggle.json` at `~/.kaggle/kaggle.json`
3. Verify: `python -m tools.kaggle_trainer.controller latest`

## First target (gates A–I)

```bash
python -m tools.kaggle_trainer.controller new-run \
  --config hercule_lm_micro --steps 100 --mode benchmark --run-id smoke-01
python -m tools.kaggle_trainer.controller status --run-id smoke-01
python -m tools.kaggle_trainer.controller logs --run-id smoke-01 --lines 40
python -m tools.kaggle_trainer.controller download --run-id smoke-01
python -m tools.kaggle_trainer.controller evaluate --run-id smoke-01 \
  --tokenizer-dir <dir>
```

Gates A–I execute inside the remote job (`smoke.json`): GPU detected,
CUDA detected, Torch backend, forward/backward, optimizer step,
checkpoint save/load, 100-step benchmark, throughput recorded. Any
gate failure aborts with a `REMOTE_FAIL [CODE]` record — never a
silent CPU fallback.

## Continuous training

`--resume`, `--continue` (new run from downloaded checkpoint),
`--evaluate`, `--status`, `--logs`, `--cancel`, `--download`,
`--latest`. Programmatic: `train_remote(model, dataset, config,
steps, gpu, resume_from=None)` returns a structured result dict.

## Safety

- Bundles exclude `.venv`, `__pycache__`, `.git`, secrets (filename +
  content scan; build refuses on hit).
- Downloaded checkpoints are registered, NEVER auto-approved.
  Adoption requires `checkpoints.adopt(run_id, reason, evidence)`.
- Failure classes: quota/accelerator/timeout retry (bounded);
  code/data/checkpoint never retried blindly.
- Execution labels: LOCAL_CPU / REMOTE_CPU(debug only) /
  REMOTE_CUDA / REMOTE_MULTI_GPU. A GPU claim requires measured
  remote telemetry.
