# N6 Final Report — 100M from-scratch pretraining

N6 STATUS: **BLOCKED** — REASON: INSUFFICIENT COMPUTE FOR PRACTICAL
100M PRETRAINING. This is a successful hardware gate, not an
engineering failure. No training was started; no fake result exists.

## Evidence chain

- Hardware (measured): i3-3220 2C/4T, ~3.6 GB free, no GPU/CUDA/torch.
- Gate (`training/n6/hardware_gate.py`): BLOCKED_NO_CUDA,
  BLOCKED_INSUFFICIENT_RAM, BLOCKED_IMPRACTICAL_TIMELINE
  (2B tokens @ 16.7 tok/s = 1,386 days > 30-day limit).
- Config frozen: 100,093,184 params, hash 2de3e5574a3bb715.
- Init proof: random Xavier, all-finite, sample hash recorded.
- Tokenizer frozen: checksum 843534c8f576ecde, round-trip tested.
- Dataset frozen: hash c9eed266… reproduced; 0 problems; [] leakage.
- Lineage defense tested (foreign checkpoints rejected).
- Sanity training green; N3/N4/N5/state suites green (64+5 skip).
- Production state: byte-identical before/after (hashes verified).
- Production default: UNCHANGED. Registry: untouched (no new
  checkpoint to register; nano/micro entries stand).
- Provenance: zero pretrained weights anywhere in N6 artifacts;
  lineage test enforces it in code.

## What N6 did not do (honestly)

No 100M weights, no training metrics beyond readiness proofs, no
arithmetic improvement, no external benchmarks, no cloud, no
purchases, no git (unauthorized).

NEXT PHASE: N7 — evaluation/validation/improvement (of the
small trained models + framework), or N6-retry on CUDA hardware
with zero pipeline changes.
