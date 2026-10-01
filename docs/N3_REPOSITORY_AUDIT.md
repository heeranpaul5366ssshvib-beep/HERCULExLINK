# N3 Repository Audit — HERCULE Original Language Model

Date: 2026-09-20 — Status: audit complete, implementation approved as below.

## 1. Existing architecture (reuse, do not duplicate)

- `brain/` — Brain, canonical `run_cycle` pipeline (sole execution path).
- `cognition/` — planner, reasoning (AdaptiveReasoningController),
  decision, experience (`ExperienceManager`), skills (`SkillManager`),
  capabilities, goals.
- `models/` — `ModelManager`, `ModelRouter`, adapters
  (`mock`/`ollama`/`transformers`/`builtin`), `models/builtin/`
  (GGUF store, llama.cpp runtime, provider). **N3 reuses the
  `BaseAdapter` provider contract; no second provider system.**
- `evaluation/framework/` — task model, runner, adapters, registry,
  scoring, reporting. **N3 reuses it; no competing framework.**
- State: `data/memory/*`, `data/tasks.json`, `data/skills/*`,
  `data/world/*` + `system/state_guard.py` + `HERCULE_TEST_GUARD`.
  **Training state lives under `training/` only, never `data/`.**
- Tests: `tests/test_*.py` hermetic conventions
  (`HERCULE_ALLOW_MOCK=1`, tmp stores, no network).
- `boot.py`, `pyproject.toml`, `requirements*.txt`,
  `installer/hercule.iss` (excludes weights — N3 adds no weights).
- No git repository present; git init NOT authorized — change
  inventory is kept in phase reports instead.

## 2. Toolchain verdict (measured, not assumed)

- torch: MISSING and uninstallable here (2.14 CPU wheel fails to
  import; CPU lacks AVX2 which modern wheels expect).
- numpy 2.5.2: present. CUDA: none. OS: Windows 10, Python 3.14.6.
- `transformers` 5.16 installed but **forbidden for N3 weights**
  (no `from_pretrained`, no checkpoints — our own code only).
- Decision: **pure-NumPy HERCULE-LM**. Fully real (hand-written
  forward/backward, AdamW, cross-entropy), zero new dependencies.

## 3. Hardware (measured)

- CPU: Intel i3-3220, 2 cores / 4 threads @ 3.3 GHz (no AVX2).
- RAM: 8.5 GB total, ~4 GB free. Disk: 39 GB free.
- GPU: Intel HD Graphics (shared) — no CUDA/ROCm; CPU training only.

## 4. Size decision

- `hercule_lm_100m` config: defined and documented (target).
- Full 100M pretraining on this CPU: **BLOCKED — INSUFFICIENT
  COMPUTE** (honest per Rule 45; ~days/weeks for meaningful tokens).
- What IS executed here: nano smoke (~1M params), overfit proof,
  and a real small-scale training run (few-M params, measurable
  loss/perplexity deltas, generation, random-control comparison).

## 5. Proposed additions (all new paths, no rewrites)

- `models/hercule_lm/` — config, BPE tokenizer (own code),
  numpy transformer, checkpoints I/O, provider adapter.
- `training/` — corpus, manifests, configs, checkpoints,
  scripts (train/evaluate/generate/prepare/validate).
- `docs/models/HERCULE-LM-100M.md`, `docs/models/HERCULE_LM_LICENSES.md`,
  `docs/N3_*.md`, `reports/N3_*.md`.
- `tests/test_hercule_lm.py` — full §37 matrix at small scale.

## 6. Risks

- NumPy CPU throughput bounds training scale (accepted; small-scale proof).
- Windows-only validation (documented; POSIX paths avoided in new code).
- No git: change tracking via file inventory in reports.
