# Phase M — Semantic Capability Intelligence

The model PROPOSES; the deterministic validator DECIDES. Semantic
inference is an additive layer over the untouched keyword path.

## Architecture

- `cognition/capabilities/proposal.py`: typed proposal contract
  (name, confidence 0..1, source, explanation, required flag,
  condition, depends_on) + strict payload parser (malformed →
  errors, never exceptions; duplicates merge; unknown fields warned).
- `cognition/capabilities/semantic.py`: `SemanticCapabilityProposer`
  (router-selected model, centralized prompt, bounded retries,
  confidence policies, shadow comparison). Never executes,
  authorizes, or registers anything. `timeout_s` accepted but
  reported UNENFORCED — the `ModelManager.generate` boundary offers
  no cancellation, and this is stated, not hidden.
- `cognition/capabilities/hybrid.py`: ONE resolver —
  deterministic + semantic → normalization (registry-backed aliases)
  → dedup → conflict notes → deterministic gate → final sets.
  Modes: deterministic / semantic_optional (default) / hybrid /
  semantic_required / shadow. Guards: negation backstop, untrusted
  grounding + untrusted-step demotion, conditional demotion,
  false-unknown rejection, policy/health/env checks, dependency edge
  validation. Proposal-only cache (validation re-runs every time).
- `cognition/capabilities/vocabulary.py`: alias table + explicit
  dependency advisories. Model-invented names are never executable.
- Planner: `create_capable_plan(..., semantic=None, proposer=None)`
  (None/False = legacy byte-identical); `configure_semantic` for
  defaults; `Brain.run_cycle(use_semantic=..., semantic_proposer=...)`
  threads through initial plan, loop, and replans. Replans inherit.
- Flags: `system/config/semantic_config.py` (dict > `HERCULE_SEMANTIC_*`
  env > safe defaults; invalid fails clearly; semantic never
  silently mandatory).

## Security boundary

MODEL PROPOSAL ≠ VALID CAPABILITY ≠ AUTHORIZED ACTION ≠ VERIFIED
RESULT. Confidence never authorizes (1.0 for ROCKET_CONTROL is still
rejected). Untrusted content lives in a separate prompt slot AND is
backstopped deterministically. Explicit user capabilities pass the
same registry + policy gates.

## Benchmarks (scripted mock — labeled everywhere)

Dataset `cognition/capabilities/datasets/capability_bench_v1.json`
(15 cases, 12 categories). `scripts/benchmark_capabilities.py`:

| leg | P | R | F1 | FP | FN |
|---|---|---|---|---|---|
| deterministic | 0.733 | 0.711 | 0.720 | 0 | 5 |
| semantic_raw (pre-validation) | 0.556 | 0.933 | 0.571 | 15 | 1 |
| hybrid | 0.822 | 0.933 | 0.838 | 10 | 1 |
| shadow (= deterministic) | 0.733 | 0.711 | 0.720 | 0 | 5 |

Reading: the mock recalls what keywords miss (paraphrase/implicit);
the validator trims its false positives (15→10) while keeping recall.
Calibration (accepted proposals): 0.90–1.00 bucket 14/22 correct
(0.636) — confidence is NOT assumed calibrated. No claim is made
about live models; live legs are env-gated and skip without weights.

## Latency (measured)

Deterministic ~0.3ms/case · mock-semantic ~0.1ms · hybrid ~0.2ms ·
shadow ~0.2ms · planner hybrid overhead negligible · full suite
unchanged (~25–33s, model-load dominated). No improvement claimed.
