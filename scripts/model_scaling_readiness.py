#!/usr/bin/env python3
"""Model scaling readiness validator for HERCULE-LM.

Calculates memory requirements for each model configuration and
classifies readiness for the current hardware.
"""

import json
import sys
from pathlib import Path

# Ensure HERCULE root is in path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch

from models.hercule_lm.config import HerculeLMConfig, load_config


def estimate_memory(config: HerculeLMConfig, batch: int, seq_len: int,
                    dtype_bytes: int = 4) -> dict:
    """Estimate memory requirements for training."""
    d = config.hidden_size
    v = config.vocab_size
    L = config.num_layers
    f = config.ffn_size
    H = config.num_heads

    # Model parameters (params + gradients = 2x)
    model_params = config.parameter_count()
    model_mem = model_params * dtype_bytes
    grad_mem = model_mem

    # Optimizer states (AdamW: m + v = 2x params, fp32)
    opt_mem = model_params * 4 * 2

    # Activations (rough estimate)
    # Per layer: [B, T, d] for ln1, qkv, attn_out, ln2, f1, f2, residual
    # Peak per layer ~ 7 * B * T * d
    # Plus embeddings: B * T * d
    B = batch
    T = seq_len
    act_per_layer = 7 * B * T * d * dtype_bytes
    embeddings = B * T * d * dtype_bytes
    total_activations = embeddings + L * act_per_layer

    # Output logits: B * T * v
    logits_mem = B * T * v * dtype_bytes

    # Total
    total = model_mem + grad_mem + opt_mem + total_activations + logits_mem

    return {
        "model_params": model_params,
        "model_memory_mb": round(model_mem / 1e6, 1),
        "gradient_memory_mb": round(grad_mem / 1e6, 1),
        "optimizer_memory_mb": round(opt_mem / 1e6, 1),
        "activation_memory_mb": round(total_activations / 1e6, 1),
        "logits_memory_mb": round(logits_mem / 1e6, 1),
        "total_training_mb": round(total / 1e6, 1),
        "total_training_gb": round(total / 1e9, 2),
        "assumptions": [
            f"dtype={dtype_bytes}B",
            "optimizer=adamw",
            "activations fully materialized (no checkpointing)",
            "excludes Python/BLAS/framework overhead",
            f"batch={batch}, seq_len={seq_len}"
        ]
    }


def check_model_readiness(model_name: str, config: HerculeLMConfig,
                          available_vram_gb: float, available_ram_gb: float,
                          batch: int = 8, seq_len: int = None) -> dict:
    """Check if a model can fit in available memory."""
    if seq_len is None:
        seq_len = config.context_length // 2

    # Try multiple batch sizes to find max feasible
    results = {}
    for b in [1, 2, 4, 8, 16, 32]:
        mem = estimate_memory(config, b, seq_len)
        total_gb = mem["total_training_gb"]
        fits_vram = available_vram_gb >= total_gb
        fits_ram = available_ram_gb >= total_gb
        results[f"batch_{b}"] = {
            "batch_size": b,
            "seq_len": seq_len,
            "total_gb": total_gb,
            "fits_vram": fits_vram,
            "fits_ram": fits_ram,
        }

    # Determine overall status
    any_fits_vram = any(r["fits_vram"] for r in results.values())
    any_fits_ram = any(r["fits_ram"] for r in results.values())
    max_batch_vram = max([r["batch_size"] for r in results.values() if r["fits_vram"]], default=0)
    max_batch_ram = max([r["batch_size"] for r in results.values() if r["fits_ram"]], default=0)

    if available_vram_gb > 0:
        status = "READY" if any_fits_vram else "BLOCKED"
        reason = "insufficient VRAM" if not any_fits_vram else ""
    else:
        # No GPU - use system RAM
        status = "READY" if any_fits_ram else "BLOCKED"
        reason = "insufficient RAM" if not any_fits_ram else ""

    return {
        "model": model_name,
        "parameter_count": config.parameter_count(),
        "architecture_hash": config.architecture_hash(),
        "seq_len": seq_len,
        "batch_results": results,
        "max_batch_vram": max_batch_vram,
        "max_batch_ram": max_batch_ram,
        "status": status,
        "reason": reason,
        "requires_cuda": available_vram_gb > 0,
    }


def main():
    # Config files can have underscores or dashes - try both
    def try_load(name):
        for variant in (name, name.replace("_", "-")):
            try:
                return load_config(variant)
            except Exception:
                pass
        return None

    models = [
        "hercule_lm_nano",
        "hercule_lm_micro",
        "hercule_lm_s10m",
        "hercule_lm_s25m",
        "hercule_lm_s50m",
        "hercule_lm_100m",
        "hercule_lm_300m",
        "hercule_lm_1b",
        "hercule_lm_3b",
        "hercule_lm_7b",
    ]

    inventory_path = Path("reports/frontier_program/hardware_inventory.json")
    if inventory_path.exists():
        inv = json.loads(inventory_path.read_text())
        available_vram_gb = 0.0
        if inv["gpu"]["cuda_available"]:
            # Use first GPU's VRAM
            available_vram_gb = inv["gpu"]["devices"][0]["total_memory_bytes"] / 1e9
        available_ram_gb = inv["memory"].get("available_bytes", 0) / 1e9
    else:
        # Fallback
        import psutil
        available_vram_gb = 0.0
        available_ram_gb = psutil.virtual_memory().available / 1e9

    print(f"Available VRAM: {available_vram_gb:.1f} GB")
    print(f"Available RAM: {available_ram_gb:.1f} GB")

    results = {}
    for model_name in models:
        try:
            config = try_load(model_name)
            if config is None:
                results[model_name] = {"status": "ERROR", "error": "Config not found"}
                print(f"{model_name}: ERROR - Config not found")
                continue
            res = check_model_readiness(model_name, config, available_vram_gb, available_ram_gb)
            results[model_name] = res
            print(f"{model_name}: {res['status']} ({res['reason']}) "
                  f"max_batch_vram={res['max_batch_vram']} max_batch_ram={res['max_batch_ram']}")
        except Exception as e:
            results[model_name] = {"status": "ERROR", "error": str(e)}
            print(f"{model_name}: ERROR - {e}")

    # Write results
    out_dir = Path("reports/frontier_program")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "model_scaling_readiness.json"
    out_file.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "available_vram_gb": available_vram_gb,
            "available_ram_gb": available_ram_gb,
        },
        "models": results,
    }, indent=1), encoding="utf-8")
    print(f"\nModel scaling readiness written to {out_file}")
    return 0


if __name__ == "__main__":
    from datetime import datetime, timezone
    sys.exit(main())