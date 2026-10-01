# N8 Results (machine records: `training/n8/results/*.json`)

Common grounds — seed-val loss / N7 / arithmetic:

| Exp | Corpus | Own-val | Common val | N7 | Arith |
|---|---|---|---|---|---|
| A (control) | seed | 2.15 | 4.48 | 0/30 | 0/30 |
| B (dedup) | unique | 2.00 | 2.77 | 0/30 | 0/30 |
| C (expanded) | expanded | 2.13 | 2.06 | 0/30 | 0/30 |
| D (2x cap) | 2x | 2.06 | 2.75 | 0/30 | 0/30 |
| E (arith) | arith | 2.16 | 3.58 | 0/30 | 0/30 |

Reference: micro1 (291 steps) common-val ≈ 1.53, N7 1/30.

## Measurement note

Re-running A's common-val gives 4.28 vs 4.48 earlier (~5% CPU
BLAS run-to-run jitter on small batch samples). All cross-candidate
gaps discussed above exceed this jitter except B-vs-D (2.77 vs
2.75 — indistinguishable, reported as such).

## Analysis (N8.26)

1. Removing shaping (B vs A): common-val 2.77 vs 4.48 — favors
   dedup, but A ran hotter early (own-val trajectory noisier);
   INCONCLUSIVE-to-weak-positive. Not a mandate.
2. Expanded (C): best common-val (2.06) — more diverse data helps
   even at fixed budget. Weak-positive (single seed).
3. Controlled 2x (D): indistinguishable from B (2.75 vs 2.77) —
   exact-2x repetition adds nothing over unique at this budget.
4. Arithmetic (E): no task transfer (0/30); common-val worst (3.58)
   — narrow data hurts generality. NEUTRAL-to-negative on
   generality, INCONCLUSIVE on longer-horizon arithmetic.
5. No N7 regression anywhere (all 0/30 = baseline band; micro1's
   1/30 came from 2x the steps).
6. Diversity up (C: +3,355 docs), cost flat (identical budgets;
   ~4–5 min/run on 2 cores).
7. Robust: dedup ≥ repetition pattern (B/D beat A on common val).
8. Inconclusive: single-seed, single-budget, 150-step horizon —
   all deltas are small-sample signals, reported as such.

No corpus declared superior. No candidate promoted. No ranking.
