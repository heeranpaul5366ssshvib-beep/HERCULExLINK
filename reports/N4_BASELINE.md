# N4 Baseline — N3 micro reproduction (N4_BENCHMARK_CONFIG v1)

Config: hercule_lm_micro (3,088,384 params), batch 8, seq 64,
seed 0, cosine lr 3e-4, clip 1.0, AdamW, float32 CPU.

| Stage | Measured |
|---|---|
| data load | 0.123 s |
| BPE train (252 merges) | 8.506 s (one-time; now cached) |
| encode + batch | 0.252 s |
| init | 0.048 s |
| forward / step | 0.512 s (29%) |
| backward / step | 0.798 s (46%) |
| clip + optimizer / step | 0.064 s (4%) |
| step mean / p95 | 1.754 s / 2.444 s |
| throughput | 292.0 tok/s |
| checkpoint save / load | timed per run (see benchmark JSONs) |
| validation | in-loop subset (configurable interval) |

PRIMARY BOTTLENECK: CPU matmul (forward + backward = ~75% of step).
SECONDARY: one-time BPE/tokenizer rebuild per invocation (~8.5 s).
EVIDENCE: per-component timers in `training/benchmark.py`; optimizer
elementwise and Python overhead account for the remainder (~5%).
No GPU exists to relieve it; no torch exists to rephrase it.
