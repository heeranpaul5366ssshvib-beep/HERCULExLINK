# N3 Final Report — HERCULE Original Language Model

## 1-2. Audits

Repository audit: `docs/N3_REPOSITORY_AUDIT.md`. Hardware: Intel
i3-3220 2C/4T, 8.5 GB RAM (~4 free), no CUDA, Win10, Py3.14, no torch
(torch wheel uninstallable/broken; AVX2 absent) → pure-NumPy design.

## 3-5. Architecture / parameters / init

Causal decoder transformer, own NumPy code. nano 933,120 · micro
3,088,384 · 100m 100,093,184 params (formula == implementation,
tested). Xavier-uniform seeding; seed-determinism tested; no
pretrained markers (tested). Float64 gradcheck over all parameter
families: worst error 2.5e-06 (one real QKV-layout bug found+fixed).

## 6. Tokenizer

Own byte-level BPE, reversible, specials <PAD>/<BOS>/<EOS>/<UNK>,
save/load with checksum manifest, round-trip tested.

## 7-8. Dataset

`hercule-seed-v1`: 6,450 paragraph docs (arithmetic 3-digit,
facts, USER/TARGET behaviors, stories), all HERCULE-authored/
MIT. License gate, empty/dup/encoding checks, hash splits
(5,960/163/327), leakage gate, eval-prompt blocklist.

## 9. Behavior data

USER/TARGET pairs only — no chain-of-thought anywhere.

## 10. Leakage control

Hash splits + contamination test + blocklist; overlap verified [].

## 11-12. Objective/loop

Cross-entropy, AdamW, cosine schedule, clip 1.0, atomic
checkpoints, resume validated, Ctrl+C safe, exit codes documented.

## 13-14. Checkpoints/reproducibility

npz + manifest (weights hash, config hash, seed, dataset hash, run
record) + `latest.json` (never sole copy). Run manifests capture
platform/versions/hyperparameters.

## 15-16. CLI/validation

`training.{train,generate,evaluate,prepare_data}`, dataset gate
refuses to train on violations (tested).

## 17-18. Smoke/overfit

Pipeline validation PASS (nano 160 steps, valid 2.67, reload,
resume, generate). Overfit PASS (loss → 0.02, ppl 1.0).

## 19. Pretraining

micro1: 291 steps / 148,544 tokens / ~9 min / ~300 tok/s, valid
1.53, ppl 4.63. **100M: BLOCKED — INSUFFICIENT COMPUTE**
(~10 tok/s projected; years for real budgets). No fake checkpoint.

## 20-23. Evaluation

Levels 1–2 measured; random control ppl 1219.6 vs trained 4.63
(real training effect); arithmetic 0/30 both (honest).
Framework subset 4/4 with explicit deterministic-component
attribution. Provider contract integrated + tested.

## 24-27. Provider/integration

`HerculeLMProvider` (generate/chat/health/metadata, offline,
honest absence). Brain routing pending further training.
Ollama untouched and optional.

## 28-29. State integrity (with one honest violation)

Training state confined to `training/`; tests use tmp dirs +
guard. **Violation:** the N3.15 integration probe ran 4 eval tasks
without isolation env, appending 2 experience records (+77→79) and
touching memory/world stores (append-only; skills/tasks untouched;
nothing deleted or overwritten). Cause identified; isolation tests
(28/28 incl. state-safety) pass.

## 30-31. Security/safety

Dataset never executed; no secrets in corpus; model proposes only;
policy/verification untouched; no self-modification surface added.

## 32-36. Registry/versions/cards/licenses

`models/registry.json` (EXPERIMENTAL, checksums/hashes),
`docs/models/HERCULE-LM-100M.md`, `docs/models/HERCULE_LM_LICENSES.md`.

## 37-38. Tests/performance

`tests/test_hercule_lm.py`: 17/17. nano ~800 tok/s, micro ~300
tok/s, checkpoint ~12 MB (micro). Correctness first; no optimization.

## 39-40. Failures/honesty

All failure modes return explicit codes; no success claims beyond
measurements above. Not intelligent/human-level/AGI — a small
genuinely-trained model plus honest negative results.

## 42. Acceptance checklist

[x] audited [x] hardware [x] documented [x] tokenizer [x] dataset
[x] validation [x] from-scratch model [x] init verified [x] loop
[x] checkpoints [x] resume [x] smoke [x] overfit [x] training done
(BLOCKED at 100M, completed at micro) [x] metrics [x] eval
[x] random control [x] local inference [x] provider [x] Ollama
optional [x] isolation (1 violation, disclosed) [x] tests
[x] docs [x] final report.
