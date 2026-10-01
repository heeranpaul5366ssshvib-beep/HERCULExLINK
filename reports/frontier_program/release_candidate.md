# October 13 Release Candidate Checklist (Phase 7Q)

## Included (validated)

- Stable model configs (nano→7B) with arch hashes + feasibility verdicts
- Stable agent Core (untouched) + adaptation loop (22+3 tests)
- Coding/research/tool-use data + verifiers + eval suites (13)
- Memory, verification, safety gates (re-run green; SAFETY suite measured)
- Benchmark report (`phase7_eval.json`), model card generator, known limitations
- Reproducible lineage (manifests, hashes, MANIFEST.json)

## Known limitations (ship-blockers if misrepresented)

- No GPU evidence: all CUDA/AMP/DDP-multi/FSDP NOT_RUN
- Untrained models score ~0 on reasoning/coding/safety suites
- SFT 20-step nano run: UNCHANGED (no improvement claim)
- Dataset-v2: validated candidate, not migrated
- Multilingual: probes only, ~0 Bengali/Hindi training data

## Release rule

Ship as an honest measured release. Any capability claim must cite a
measured `baselines.compare` delta or a MEASURED report row.
