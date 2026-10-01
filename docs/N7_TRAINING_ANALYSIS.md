# N7 Training-Curve Analysis (micro1, from recorded history)

- Train loss: ~6.6 → 0.6–1.5 band over 291 steps. Valid: → 1.53.
- No divergence, no NaNs (NaN guard would have aborted with
  TRAINING_DIVERGED). Gradient norms 1.7–3.7, no explosion.
- No overfitting signal at this budget (valid tracks train down;
  gap small). No plateau reached (loss still falling at step 291).
- Overfit control (repetitive set): loss → 0.02 — pipeline
  responsive, not saturated.
- Limitation: per-step logs were stdout-only in N3 (not retained
  as files); N7 `training/n7/eval_results_*.json` and benchmark
  JSONs are the machine-readable records going forward.
- No intelligence claims drawn from curves; they show optimization
  health only.
