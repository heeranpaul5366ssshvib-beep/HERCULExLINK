# Dataset v2 Quality Report (Phase 4I) — hercule-seed corpus

**Status: MEASURED on the real seed corpus. Candidate filtered corpus only —
the training pipeline still uses the raw corpus (unchanged).**

## Pipeline

`models/hercule_lm/dataset_v2.py::build_dataset`:
validate → filter (`min_chars=20`, license allowlist) → exact dedup →
near-dedup → language scan → quality scores → contamination probes →
hash splits → manifest. Machine record: `dataset_v2.json`.

## Results

| Stage | Docs |
|---|---|
| input (paragraphs) | 6450 |
| after length filter (<20 chars dropped: 480) | 5970 |
| after exact dedup (removed: **2710**) | 3260 |
| near-dedup (full scan skipped: 3260 > cap 2000) | 3260 |

- **Dataset hash (v2 candidate): `8eca4ebe32032298297b0f23b5b6111e4b85880f2b66ef6ea97da8f05c653819`**
- Splits: train 2951 / validation 159 / test 150, leakage overlap: none
- Near-dup on documented 500-doc sample: 0 groups, 0 removed
- Contamination probes (3 listed probes): **0 hits**

## Key finding

~42% of seed paragraphs are byte-exact duplicates. The seed corpus is
small/synthetic; duplication is expected, but any future scale-up must
budget for dedup at ingest (v2 does this) rather than after tokenization.

## Languages (script-heuristic, labeled as such)

`other: 3000, english: 260`. `other` here means symbol/digit-heavy
lines (code, math, punctuation) that are <50% Latin-alpha — an artifact
of paragraph-level chunking plus a script heuristic, not a trained
identifier. Bengali/Hindi coverage in the seed corpus: ~0 — the
multilingual target (Phase 4H) requires new sourced data, not
relabeling.

## Quality scores (documented heuristic)

Mean 0.667; 0 docs < 0.5; 233 docs ≥ 0.8. Scores are filter signals,
never truth verdicts. No score-based filtering was applied
(`min_score=0.0`).

## What v2 does NOT change

- Tokenizer (checksum-gated cache untouched)
- Training corpus (train.py still consumes raw docs + manifests)
- Splits methodology (same hash-split; leakage-free verified)
- Licensing gate (same allowlist; GPL test doc correctly rejected in tests)

## Gaps for the multilingual/large-scale corpus

1. Bengali/Hindi/English balanced sourcing with licenses + provenance
2. Full-corpus near-dedup above the 2000-doc cap (sharded offline run)
3. Wider contamination probe list (current: 3 probes, documented)
4. Shard writer exists (`write_shards` + `ShardedStream` cursor); not
   yet wired into the trainer's hot path (cached streams still used)
