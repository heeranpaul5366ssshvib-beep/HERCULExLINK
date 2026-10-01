# N3 Training Pipeline Validation

Date: 2026-09-20. Verdict: **N3 TRAINING PIPELINE VALIDATION — PASS**
(not a language-model success claim).

## Gradcheck (float64 finite differences, 22 probes, all param families)

Worst relative error 2.5e-06 → **PASS**. One genuine bug found and
fixed by this check (QKV gradient layout must be per-head
[Qh Kh Vh]); probe indices were then diversified so coincidental
passes cannot recur.

## Smoke (nano 0.93M, seed corpus, 160 steps, batch 8)

- loss 6.6373 → ~2.9 train; valid 3.5181 → 2.6695, ppl 33.7 → 14.4.
- ~800 tok/s on 2-core CPU. Checkpoints at 60/120/160 + final.
- Reload → generate works. Resume from step_00000120 → 160 works
  (valid kept improving). No NaNs, no divergence.

## Overfit (nano, 40-doc repetitive set, 300 steps, lr 1e-3)

- loss → 0.0199, ppl 1.0. Gradients/optimizer/loss provably connected.

## Negative controls

- Empty validation split → honest fallback message, no crash.
- Corrupt checkpoint arch mismatch → CHECKPOINT_MISMATCH raised.
- Unbound save → refused with warning, returns False.
