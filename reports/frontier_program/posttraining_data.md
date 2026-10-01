# Post-Training Data (Phase 6A) — `postdata-v1`

**Status: IMPLEMENTED + TESTED. 200 train / 100 eval samples, hash-disjoint.**

## Schema

Every sample: id, task, language, source, license, version, split,
prompt, response (+ tools/schema/tests/reference where applicable),
validated, contaminated. License: HERCULE-authored (MIT, repo);
source: hercule-synthetic (no external data, no pretrained content).

## Coverage (per split)

instruction, coding, math, reasoning, planning, tool_use,
structured_json, research, multilingual (en/bn/hi), safety.

## Integrity

- Train/eval id overlap: none (verified, `verify_disjoint`)
- Held-out eval: disjoint id range + different seed
- Artifacts: `training/data/posttrain/sft_train.json`, `sft_eval.json`
- Machine record: `posttraining_data.json`

## GPU status

Builders are CPU-deterministic. GPU SFT training reuses the torch
trainer (`--sft-marker`) when hardware exists; smoke-tested on CPU.
