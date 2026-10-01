# HERCULE-LM License Audit

## HERCULE-authored (MIT, this repo)

- `models/hercule_lm/` — architecture, tokenizer, training, checkpoints I/O, provider.
- `training/` — corpus builders, CLI shims, seed corpus texts.
- HERCULE-LM weight checkpoints (`training/checkpoints/*`) — trained
  by HERCULE code from random initialization on HERCULE-authored data.

## Third-party software (not owned by HERCULE)

- NumPy 2.5.2 (BSD-3) — tensor math only; no models, no weights.
- Python standard library (PSF) — JSON, IO, hashing, CLI.
- pytest (MIT) — tests only.

## Third-party data: none

- Seed corpus is HERCULE-authored/synthetic (general facts stated in
  plain words, generated arithmetic, synthetic stories). No scraped,
  copyrighted, or user data. No evaluation answers in training pairs
  (3-digit training operands; exact eval prompt strings blocklisted).

## Third-party algorithms/research (ideas, own code)

- Transformer decoder, BPE, AdamW, cosine schedule, Xavier init —
  public research methods re-implemented from scratch in NumPy.
  `transformers`/`tokenizers`/`torch` libraries are NOT used by
  HERCULE-LM (torch is not installed; `transformers` present in the
  environment is never imported by this code).

## What HERCULE may claim

"HERCULE-trained from-scratch language model" — weights randomly
initialized in-repo, training actually executed and logged, no
pretrained weights imported. This claim covers nano/micro
checkpoints only; the 100M config is untrained (no such claim).
