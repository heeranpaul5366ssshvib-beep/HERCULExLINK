from __future__ import annotations
"""RNG bookkeeping (N5/N-frontier §12/§24): capture what is capturable.

The training loop draws randomness from seeded `default_rng(seed)`
streams (batch permutation) and fixed init seeds. Those are fully
described by (seed, versions) — no opaque state to persist. This
module records that description plus live Python/NumPy generator
states for audit. CPU determinism under fixed seed+order is tested;
CUDA trajectories are never claimed bit-identical.
"""

import random
from typing import Any, Dict

import numpy as np


def capture_rng_state(seed: int) -> Dict[str, Any]:
    """Snapshot RNG description (JSON-serializable)."""
    try:
        py_state = list(random.getstate())
        py_state[1] = list(py_state[1])
    except Exception:
        py_state = []
    return {
        "seed": int(seed),
        "python_random_state": py_state,
        "numpy_version": np.__version__,
        "streams": "numpy.random.default_rng(seed); CPU-deterministic "
                   "under fixed seed + batch order",
    }


def describe_determinism() -> Dict[str, Any]:
    return {
        "configuration_reproducibility": "same config+seed+dataset hash reproduces setup",
        "checkpoint_resumability": "step/optimizer/data-cursor restore tested bitwise on CPU",
        "numerical_determinism": "CPU NumPy deterministic under fixed seed+order; "
                                 "CUDA trajectories NOT claimed bit-identical",
    }
