# N5 Reproducibility

Three distinct properties (documented, not conflated):

1. CONFIGURATION REPRODUCIBILITY — same config + seed + dataset
   hash + code reproduces the setup (run/dataset manifests record
   everything; determinism test passes).
2. CHECKPOINT RESUMABILITY — step, optimizer, scheduler position
   restore exactly on the same platform (round-trip tested,
   including fresh-process reload).
3. NUMERICAL DETERMINISM — guaranteed only for fixed CPU/NumPy
   trajectories. CUDA trajectories are NOT claimed bit-identical;
   equivalence criteria for a future CUDA backend: shapes, finite
   outputs, sane loss, valid gradients, checkpoint compatibility —
   not bitwise equality.
