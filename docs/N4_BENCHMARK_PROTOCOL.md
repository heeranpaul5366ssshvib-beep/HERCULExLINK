# N4 Benchmark Protocol (N4_BENCHMARK_CONFIG v1 — do not change casually)

Command: `python -m training.benchmark --config <name> --steps N
--batch B [--seq-len S] [--seed 0] [--out training/benchmarks]`.

Fixed: seed, dataset (hercule-seed-v1), optimizer (AdamW 3e-4 in
harness), clip 1.0, float32 CPU, component timers, Win32 peak RSS,
checkpoint save/load + roundtrip check. Records carry timestamp,
machine, CPU/RAM/GPU, Python/NumPy/torch(None)/CUDA(false), model
config + hash, dataset/tokenizer identity, batch/seq/steps/seed.

Comparing runs: same config + same batch/seq + same commit of
`models/hercule_lm/`. Thread env (`HERCULE_LM_THREADS`) is recorded
only implicitly — note it when comparing across machines.
