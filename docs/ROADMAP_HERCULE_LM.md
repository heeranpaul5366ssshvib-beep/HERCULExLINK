# HERCULE-LM and Reasoning Research Roadmap

**Version:** 1.0  
**Status:** DRAFT — verified against repository evidence as of 2026-09-25

---

## Required Statement

> **HERCULE-LM is the long-term intended primary intelligence for HERCULEX. Current product runtime capability, optional model-backend capability, HERCULE-LM capability, and research hypotheses must be measured and reported separately.**

---

## Stage R0 — Reproducible Experiment Baseline

**Purpose:** Every experiment should record, where available:
- Experiment ID, timestamp, Git commit, runtime version
- Environment: OS, Python/PyTorch versions
- Hardware: CPU, RAM, GPU, VRAM
- Seed, model configuration, tokenizer version
- Dataset manifest or hash, token count
- Hyperparameters, training duration
- Output artifacts, checkpoint path/hash
- Evaluation suite, known limitations

**Implementation:** Use repository-native JSON/JSONL under `reports/experiments/` (create if needed). Do not require paid services or cloud tracking systems. Prefer existing tracking architecture if available.

**Acceptance Criteria:**
- `python -m hercule.experiments log --help` shows schema
- Every training/evaluation run produces a record
- Records are queryable and human-readable
- No external dependencies for logging

**Non-goals:** Cloud experiment tracking, paid SaaS integration

---

## Stage R1 — Training Backend Correctness

**Goal:** Prove infrastructure correctness before scale.

**Required Targets:**
- CPU reference behavior (forward/backward/optimizer update)
- Checkpoint save/load/resume behavior
- Small fixed-seed reproducibility where practical
- Clear CUDA availability detection (code path exists in `models/hercule_lm/device.py`)
- Actual CUDA execution evidence **only when a CUDA GPU exists** — no fake GPU support claims

**Current Verified State (from repository evidence):**
- `models/hercule_lm/train_torch.py` — PyTorch training loop with gradient accumulation, AMP, gradient clipping
- `models/hercule_lm/torch_model.py` — Transformer implementation (RMSNorm, RoPE, SwiGLU, grouped-query attention)
- `models/hercule_lm/device.py` — CUDA detection with graceful CPU fallback
- `models/hercule_lm/checkpoint.py` — save/load with manifest, RNG state, optimizer state
- `models/hercule_lm/config.py` — architecture configs (nano, micro, 100M, etc.)
- N4 feasibility report: **100M tokens ≈ 69 days, 2B tokens ≈ 3.8 years on i3-3220 / 8.5 GB RAM / no GPU** → large-scale training NOT FEASIBLE on current hardware

**Non-goals:**
- Large-scale training on current i3-3220/no-GPU hardware
- Pretending a CUDA code path was validated without CUDA hardware
- Training billions of tokens locally

**Acceptance Criteria:**
- `python -m models.hercule_lm.train_torch --dry-run --tokens 1000` completes without error on CPU
- Checkpoint save/load round-trip produces identical forward pass
- CUDA path is clearly gated behind `torch.cuda.is_available()` with logged warning when unavailable

**Dependencies:** PyTorch installed, tokenizer trained

---

## Stage R2 — Bounded Small Experiments

**Goal:** Run small experiments that produce real, reproducible evidence.

**Requirements:**
- Small model/configuration (nano: 12M params or micro: 30M params)
- Bounded data (≤ 10M tokens)
- Fixed compute/token budget (e.g., 1 GPU-hour equivalent on CPU)
- Baseline comparison (random init vs. trained)
- Loss/metric output logged per step
- Checkpoint artifact saved
- Frozen evaluation where applicable (ARC internal, evaluation suites)
- Written report of result and limitation

**Current Verified State:**
- Tokenizer training works (`training/tokenizer/` — BPE, multiple configs tested in N7/N8)
- Nano model (12M) trains at ~2000 tok/s on CPU (N7/N8 reports)
- Evaluation harness exists (`models/hercule_lm/eval_harness.py`)

**Recommended First Experiment:**
```bash
# Train nano (12M) on 1M tokens of controlled corpus
python -m models.hercule_lm.train_torch \
  --config nano \
  --tokens 1_000_000 \
  --batch-size 32 \
  --seq-len 512 \
  --out reports/experiments/nano_1M_$(date +%s)
```
- Expected: ~8 minutes on current hardware
- Evaluation: ARC internal suite + hercule_internal suite
- Report: loss curve, eval accuracy, latency, checkpoint hash

**Success Definition:** Reproducible measurement with interpretable result, not a large model or marketing claim.

**Dependencies:** R1 training backend correctness, tokenizer

---

## Stage R3 — ARC/Program-Search Reasoning

**Goal:** Improve compositional reasoning while preserving honest evaluation.

**Current Verified State (from `arc_reasoning/` + tests):**
- Relation-conditioned copy/place with 64 → 16 → 1 parsimony funnel
- Invariance checks: landmark_translation, canvas_padding, background_recolor (core); palette_rename reported only
- Selectors: shape, color, area, orientation, unique-color/shape/size, most/least-frequent-color
- Placements: onto_marker, align_bbox, adjacent, between, mirrored_across, repeated_k
- Candidate ranking: heavy local-rewrite penalty (10×/20×), relation predicate bonus
- 40 tests passing (39 ARC + 1 funnel test)
- Current benchmark: 7/128 tasks solved on discovery split (baseline v3)

**Requirements:**
- Preserve frozen task split discipline (never alter benchmark tasks to improve scores)
- Record: raw hypotheses → after parsimony funnel → invariance survivors → selected candidate
- Record intended-rule rank when known
- Record test-grid exact result
- Record timeout/search budget
- Separate generated, accepted, selected, and correct rules in reports

**Current Known Research Issue:**
Relation-conditioned-copy tasks can yield many exact-fit and invariant hypotheses. The current parsimony features (selector_bits + placement_rank) may not distinguish the intended `onto_marker` relation from competing `adjacent` or `align_bbox` variants.

**Next Priority (in order):**
1. **Counterfactual discrimination:** Insert distractors that break spurious `align_bbox`/`adjacent` matches but preserve `onto_marker`
2. **Independent landmark/source transformations:** Test that rule tracks landmark when source also moves
3. **Distractor insertion tests:** Extra objects that create false selector matches
4. **Cross-example role consistency:** Verify selector picks same role across all training pairs
5. **Whole-task compression/generalization signals:** Prefer rules that compress the task description

**Non-goals:**
- Adding large numbers of new primitives before showing existing tied candidates can be differentiated more reliably
- Claiming ARC-AGI-2 progress without frozen public evaluation

**Acceptance Criteria:**
- New discriminator reduces 64→16 funnel to ≤8 candidates on marker-tracking tasks
- Correct `onto_marker` rule ranks #1 in ≥80% of marker-tracking tasks
- All 40 existing tests still pass
- Frozen discovery split score reported honestly

**Dependencies:** R0 experiment logging, R2 small experiment infrastructure

---

## Stage R4 — HERCULE-LM Integration Gate

**Goal:** Define the evidence required before HERCULE-LM becomes the HERCULEX default backend.

**The Gate Must Include:**
- [ ] Runnable inference path (provider registered, health check passes)
- [ ] Tested model selection/routing (ModelManager routes to HERCULE-LM when preferred)
- [ ] Task-specific quality evaluation (comparison to current configured backends on HERCULEX's actual tasks: hercule_internal, ARC, coding, reasoning)
- [ ] Latency/resource measurement (mean/p95, RAM/VRAM)
- [ ] Stable failure behavior (honest errors, no fabricated responses)
- [ ] Safety/policy compatibility (approval gates work, no silent mutations)
- [ ] Transparent model identity (logs show `provider=hercule-lm`, `model=<checkpoint-id>`)
- [ ] Reproducible versioned checkpoint (manifest + architecture hash)
- [ ] No unsupported general-intelligence claims

**Current Verified State:**
- `models/hercule_lm/provider.py` implements BaseAdapter contract
- `ModelManager` can route to `hercule-lm` when `provider_pref == "builtin"` and model exists
- Checkpoint loading works for trained checkpoints (N3/N7/N8)
- No HERCULE-LM checkpoint is currently the default (Ollama/builtin GGUF preferred per `model_manager.py`)

**Explicit Status:** **This gate is NOT currently passed based on verified repository evidence.** No HERCULE-LM checkpoint has been evaluated against HERCULEX's actual task suite with quality/latency/safety comparison to the current Ollama/builtin backend.

**Acceptance Criteria:** All gate items checked with evidence in `reports/experiments/integration_gate_<timestamp>.json`

**Dependencies:** R1–R3 complete, HERCULEX P4 model transparency

---

## Hardware/Training Feasibility Summary (Verified)

| Workload | Current Hardware (i3-3220, 8.5 GB RAM, no GPU) | Feasible? |
|----------|-----------------------------------------------|-----------|
| Nano (12M) 1M tokens | ~8 min | ✅ Yes |
| Micro (30M) 10M tokens | ~2 hours | ✅ Yes |
| 100M tokens (any config) | ~69 days | ❌ No (time-bound) |
| 2B tokens | ~3.8 years | ❌ No |
| CUDA training | No GPU | ❌ No |

**Recommendation:** Focus research on CPU-feasible experiments (nano/micro, ≤10M tokens) and reasoning improvements that don't require large-scale training. A CUDA-class machine reuses the entire pipeline unchanged per N4 report.

---

## Claims Policy (Enforced in This Roadmap)

- Runtime capabilities must be attributed to the HERCULE runtime.
- Capabilities that depend on an optional third-party model must be attributed to that configured model backend plus HERCULE runtime integration.
- HERCULE-LM capabilities require evidence from an actual HERCULE-LM checkpoint and reproducible evaluation.
- Research hypotheses must be labeled as hypotheses.
- No benchmark or evaluation result may be generalized beyond its measured suite.
- No unsupported AGI, frontier-model, or universal-intelligence claim may be made.