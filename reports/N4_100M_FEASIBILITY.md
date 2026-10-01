# N4 100M feasibility — classification: NOT FEASIBLE ON CURRENT HARDWARE

## Measured throughput

100M config, batch 2 × seq 256: **16.7 tok/s**, 30.65 s/step,
peak RSS 3,998 MB (~4.0 GB free). Config: AdamW, cosine, clip 1.0,
float32 CPU — same recipe as the validated micro run.

## Time estimate (with uncertainty, not a promise)

- Chinchilla-scale budget (20 tok/param): 2.0B tokens.
  2.0e9 / 16.7 ≈ 1.2e8 s ≈ **3.8 years**, plus validation,
  checkpointing (~tens of seconds per GB written), startup,
  interruptions, and likely thermal throttling on longer runs
  (NOT MEASURED — no multi-hour run performed).
- Token-poor budget (100M tokens, far below Chinchilla): ≈ 69 days.
- Even 10M tokens (≈ one week) buys only a smoke-scale result.

## Memory verdict

Fits at b2×256 with ~zero headroom; larger batches/contexts are
OOM territory. Memory is a constraint but not the binding one.

## Binding constraint

Throughput. The CPU delivers 16.7 tok/s where ~2,000+ tok/s would
be needed to finish a serious budget in weeks. No software
optimization available here closes a ~100× gap (accepted N4 wins
total ≈ 5–10% plus one-time setup savings).

## Hardware requirement (class, not a purchase order)

A CUDA-capable GPU with ≥ 8 GB VRAM would move this workload by
roughly two orders of magnitude (evidence basis: standard
industry throughput ratios for transformer training, not a
guarantee for this box). On such hardware the N4 recipe
(cache-gated data, atomic checkpoints, cosine schedule) transfers
unchanged. CPU-only alternatives (more x86 cores) scale
approximately linearly with core count and cannot close the gap
on a desktop budget.

N3's BLOCKED verdict stands, now with measured evidence instead
of projection. No training plan is produced (per §51, a plan
requires feasibility); this file serves §41's hardware-requirements
role instead.
