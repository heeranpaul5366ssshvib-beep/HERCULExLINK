# N7 Evaluation

- Harness: `training/n7/run_eval.py` (greedy, temperature 0, fixed
  max tokens) + `models/hercule_lm/evaluate.py` (loss/ppl/token-acc/
  arithmetic + `--out` records).
- Eval set: `training/n7/eval_set.json` (30 items, 12 categories,
  checksum bc6d6e2d8c5b61b1) + manifest (seed 77031).
- Contamination: exact/normalized/sample 0% (4 initial overlaps
  found, reworded deterministically, re-verified). Bigram 63% =
  shared English vocabulary (benign, documented).
- Results (ACTUAL): micro1 1/30 (ctx-00), random 0/30; micro
  valid 1.532/ppl 4.63/token-acc per record; random ppl 1219.6.
- Attribution (§21): framework subset passes are deterministic
  components; model-level evidence is ppl/accuracy deltas only.
