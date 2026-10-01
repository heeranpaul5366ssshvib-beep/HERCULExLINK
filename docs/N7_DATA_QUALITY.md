# N7 Data Quality (measured 2026-09-20, `training/n7/data_quality_report.json`)

- Samples: 6,450 paragraphs. Empty: 0. Invalid UTF-8: 0.
- Duplicates: 3,184 — BY CONSTRUCTION (facts ×40 shuffles, behavior
  template cycling for frequency shaping), not corruption. Recorded
  here rather than silently deduplicated; a future frequency-ablation
  may revisit it.
- Short (<10ch): 0. Long (>2000ch): 0. Repeated-char anomalies: 0.
- Tokenizer failures: none (without tokenizer loaded in this run;
  field present for tokenizer-bound runs).
- Char length p50/max: 32/77. Filtering applied: none.
