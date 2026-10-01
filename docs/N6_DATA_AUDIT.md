# N6 Data Audit (via `training.prepare_data`, rebuilt 2026-09-20)

- Documents: 6,450 paragraphs across 4 files (arithmetic, facts,
  behaviors, stories). Empty: 0. Duplicates: 0. Encoding failures: 0.
- Licenses: all `HERCULE-authored (MIT, repo)`; no third-party text.
- Splits: train 5,960 / validation 163 / test 327 (hash-deterministic).
- Leakage overlap: [] (verified). Dataset hash reproduced exactly
  from N3 (`c9eed266…`), proving corpus reproducibility.
- Filtering: nothing removed (no silent deletions to report).
- Eval contamination: 3-digit training operands; exact suite prompt
  strings blocklisted in the builder; verified by construction.
- Secrets/PII scan: corpus is generated from templates + authored
  fact list; no user data, credentials, or secrets present by
  construction (templates contain no such fields).
