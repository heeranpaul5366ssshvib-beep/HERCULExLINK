# N4 Final Report — training acceleration, profiling & scaling

## 1. Executive summary

Measured everything, optimized the honest parts (+~5% step, −100%
repeat setup costs), proved 100M runs but cannot finish here.
Classification: **NOT FEASIBLE ON CURRENT HARDWARE**.

## 2-4. Baseline / hardware / profiling

N3 micro reproduced under `N4_BENCHMARK_CONFIG v1`: 292 tok/s,
fwd 29% / bwd 46% / opt 4%. i3-3220 2C/4T, 8.5 GB RAM, no GPU,
no torch. Bottleneck: CPU matmul. Secondary: repeat BPE/tokenizer
rebuilds (now cached).

## 5-8. Optimizations attempted / accepted / rejected

Accepted 4 (stream cache, tokenizer cache, thread helper,
benchmark harness). Rejected 2 with measurements (gc off, logical
threads). Not-applicable 5 (all torch/GPU items — declared, never
faked). Full ledger: `reports/N4_OPTIMIZATION.md`.

## 9-11. Benchmark / scaling / memory

Scaling table (§21 in `reports/N4_SCALING.md`): 0.93M→784 tok/s
through 100M→16.7 tok/s, all measured with peak RSS and checkpoint
sizes. Memory: 1.6 GB theoretical floor + ~2.4 GB activations at
b2×256 = 4.0 GB measured peak.

## 12. 100M estimate

2B-token budget at 16.7 tok/s ≈ 3.8 years ± validation/checkpoint/
thermal outage overhead. 100M tokens ≈ 69 days. Time-bound, not
just memory-bound.

## 13-15. Correctness / quality / state-safety

No model-semantics change in N4; determinism + gradcheck suites
pass; micro quality re-measured identical (valid 1.53, arith 0/30);
production hashes unchanged across N4 (verified before/after).

## 16. Tests

N3: 17/17. N4: 5/5 (threads, cache equivalence+invalidation,
determinism, benchmark schema, scaling counts). State safety:
11/11. Total N3+N4+state: 33/33 in the N4 regression slice.

## 17-19. Limitations / feasibility / next

100M: NOT FEASIBLE ON CURRENT HARDWARE (evidence above).
N3's BLOCKED stands, upgraded from projection to measurement.
Next: a CUDA-class machine reuses this entire pipeline unchanged;
or authorize a token-poor 100M smoke (weeks) explicitly — not
recommended as "pretraining".
