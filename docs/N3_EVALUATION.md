# N3 Evaluation

## Levels

1. Training health: loss, validation loss, perplexity, gradient norms,
   NaN guards (`training.evaluate --checkpoint`).
2. Language: held-out 3-digit arithmetic exact-match + samples.
3. HERCULE tasks: intent/structured/planning/tool/skill/verification/
   honesty/safety — via `evaluation/framework` with a hercule-lm
   provider registered (integration test proves the routing path;
   task credit is attributed per §21 below).
4. HERCULE integration: full pipeline runs with the provider bound.

## Attribution rule (§21)

Model vs system performance are recorded separately. Deterministic
HERCULE components (routing, memory probes, verified tool math) can
pass tasks with zero model contribution — the random-control
comparison (untrained vs trained checkpoint on identical suites) is
the only accepted evidence of training effect.

## N3_MODEL_EVALUATION suite

`python -m models.hercule_lm.evaluate` output is the dedicated
suite record; framework-level 64-task runs with hercule-lm bound
are reported with explicit attribution notes.
