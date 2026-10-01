from __future__ import annotations
"""Resource estimators (N5 §19/§20): labeled ESTIMATES, never measurements.

Memory separates weights / gradients / optimizer / activations /
checkpoint. Time derives from a measured tokens/sec figure supplied
by the caller (see training/benchmark.py). Uncertainty is explicit.
"""

import math
from typing import Any, Dict


def estimate_memory(parameter_count: int, batch: int, seq_len: int,
                    hidden: int, layers: int, heads: int, vocab: int,
                    dtype_bytes: int = 4, optimizer: str = "adamw") -> Dict[str, Any]:
    """ESTIMATE (MB) for fp32 AdamW training. Activations scale with B*T."""
    params = int(parameter_count)
    weights = params * dtype_bytes
    grads = params * dtype_bytes
    opt_mult = 2.0 if optimizer.lower() == "adamw" else 1.0
    opt_state = params * dtype_bytes * opt_mult
    # Activations (rough, fp32): embeddings + per-layer norms/attn/FFN
    # plus attention score matrices (B*H*T*T).
    per_tok = hidden * (8 + 4 * layers) + heads * seq_len
    activations = batch * seq_len * per_tok * dtype_bytes
    total = weights + grads + opt_state + activations
    return {
        "kind": "ESTIMATE",
        "model_memory_mb": round(weights / 1e6, 1),
        "gradient_memory_mb": round(grads / 1e6, 1),
        "optimizer_memory_mb": round(opt_state / 1e6, 1),
        "activation_memory_mb": round(activations / 1e6, 1),
        "checkpoint_memory_mb": round((weights + opt_state) / 1e6, 1),
        "total_training_mb": round(total / 1e6, 1),
        "assumptions": [f"dtype={dtype_bytes}B", f"optimizer={optimizer}",
                        "activations fully materialized (no checkpointing)",
                        "excludes Python/BLAS/framework overhead"],
    }


def estimate_time(tokens_per_sec: float, target_tokens: int) -> Dict[str, Any]:
    """ESTIMATE wall time from a MEASURED throughput figure."""
    if tokens_per_sec <= 0 or target_tokens <= 0:
        raise ValueError("tokens_per_sec and target_tokens must be positive")
    seconds = target_tokens / float(tokens_per_sec)
    out = {"kind": "ESTIMATE", "seconds": round(seconds, 1),
           "hours": round(seconds / 3600, 2),
           "days": round(seconds / 86400, 2),
           "years": round(seconds / 31536000, 3),
           "uncertainty": ["excludes validation/checkpointing/startup",
                           "excludes interruptions and thermal throttling",
                           "assumes sustained measured throughput"]}
    return out


def format_duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f}min"
    if seconds < 86400 * 3:
        return f"{seconds / 3600:.1f}h"
    if seconds < 31536000 * 2:
        return f"{seconds / 86400:.1f}d"
    return f"{seconds / 31536000:.2f}y"


def memory_for_config(config, batch: int, seq_len: int) -> Dict[str, Any]:
    return estimate_memory(config.parameter_count(), batch, seq_len,
                           config.hidden_size, config.num_layers,
                           config.num_heads, config.vocab_size)
