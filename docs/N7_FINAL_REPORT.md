# N7 Final Report — evaluation, data quality & readiness

N7 STATUS: PASS (evaluation/readiness phase; no 100M training started,
none claimed).

## Measured results

- Eval set: 30 items / 12 categories, checksum bc6d6e2d8c5b61b1.
- micro1: 1/30 (ctx-00 recall). random: 0/30. ppl 4.63 vs 1219.6.
- Contamination: 0/0/0 exact/normalized/sample (4 found → fixed →
  re-verified); bigram 63% benign shared vocabulary.
- Quality: 0 empty/invalid; 3,184 duplicates by construction
  (documented frequency shaping, not hidden).
- Tokenizer: frozen, deterministic, round-trip green.
- Lineage/init: enforced in code + artifacts; foreign rejected.
- Generation: deterministic (same ckpt/prompt/settings/seed).
- Roundtrip/resume: equivalent incl. resume-equals-uninterrupted.
- Adapter: provider contract tested; policy/verification untouched.
- Perf (MEASURED): tok load 27 ms, model load 400 ms, gen 58.6 tok/s
  (micro greedy), peak RSS 78.5 MB.
- Registry: 100M entry = CONFIGURED/NOT_TRAINED (factual).
- 100M TRAINING: NOT STARTED (gate BLOCKED, machine unchanged).

## Suites

N3 17/17 · N4 5/5 · N5 21+5sk · N6 10/10 · N7 13/13 · state 11/11.
Production hashes unchanged (verified before/after).

## Limitations / next

Small-model arithmetic 0/30; eval set is a probe, not a universal
benchmark; CUDA/AMP/multi-GPU absent by hardware. NEXT: N8 —
architecture/data/optimization direction from N7 evidence.
