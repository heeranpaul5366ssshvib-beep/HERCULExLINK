# N8 Arithmetic Analysis

- All candidates (A–E) plus micro1: 0/30 held-out exact-match.
- E (arithmetic-targeted, ~95% arithmetic tokens) still 0/30, but
  generations show learned arithmetic SHAPE ("al + + + +") rather
  than random tokens — format without computation at 150 steps.
- Overlap audit: 0/30 eval pairs occur in E's training (exact or
  operand-swapped), so the test measures generalization, and the
  honest result is failure at this scale/budget.
- Conclusion: 150 steps × 3M params does not induce arithmetic,
  regardless of corpus mix. No regression vs baseline (also 0/30);
  no improvement claimed. Longer budgets / larger models are the
  evident next lever (future phase, not started here).
