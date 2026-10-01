# N3 Dataset Spec — hercule-seed-v1

Hash: `c9eed26632487bff9addaea4dcf3aaf35e1256616c9cabdb31ef7a8b748f7574`
(post paragraph-split rebuild; manifests embed per-run hashes).

## Sources (all HERCULE-authored/synthetic, MIT)

| Source | Origin | License | Content |
|---|---|---|---|
| hercule-arithmetic-v1 | synthetic (seed 20260920) | HERCULE-authored | 3000 Q/A arithmetic, 3-digit operands |
| hercule-facts-v1 | authored | HERCULE-authored | 20 facts × 40 shuffles |
| hercule-behaviors-v1 | authored | HERCULE-authored | 1200 USER/TARGET pairs (routing, planning, honesty, refusal templates) |
| hercule-stories-v1 | synthetic (seed 20260920) | HERCULE-authored | 250 short paragraphs |

~6,450 paragraph documents after splitting (train ~5,960 / val ~163 / test ~327 by document hash).

## Rules enforced in code

- Licenses allowlisted (`validate_documents` refuses otherwise).
- Empty/duplicate/unencodable documents refused.
- Train/val/test split by document hash; `check_no_leakage` gate.
- Eval contamination: exact HERCULE-suite prompt strings blocklisted
  in the builder; training arithmetic uses 3-digit operands (suite
  items use small ints; whole-item overlap impossible by construction).
- No chain-of-thought anywhere: USER/TARGET pairs are observable
  outputs only.
