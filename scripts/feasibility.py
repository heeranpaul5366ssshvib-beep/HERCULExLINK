#!/usr/bin/env python3
"""Training feasibility engine (Phase 3J).

Combines MEASURED throughput (CPU from Phase 2 benchmarks, CUDA when
available) with ESTIMATED memory to project per-model training
feasibility. Evidence classes are kept separate and labeled:

- MEASURED_CPU / MEASURED_CUDA : real benchmark numbers
- ESTIMATED                   : memory/projection math
- HISTORICAL                  : stale tables (labeled, never mixed)
- NOT_RUN                     : no measurement exists
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.hercule_lm.config import load_config
from models.hercule_lm.estimate import estimate_memory, estimate_time


# MEASURED_CPU: Phase 2 steady-state torch-CPU tok/s (batch 8, FP32).
MEASURED_CPU_TOKS = {
    "hercule-lm-micro": 554.0,
    "hercule-lm-s10m": 182.0,
}

# Throughput scales ~linearly with params on the same device for this
# arch family; used ONLY to project ESTIMATED tok/s where unmeasured.
REF_MODEL, REF_PARAMS = "hercule-lm-s10m", 10561024


def projected_cpu_toks(params: int) -> float:
    return MEASURED_CPU_TOKS[REF_MODEL] * REF_PARAMS / max(1, params)


def _free_ram_gb() -> float:
    try:
        import psutil

        return float(psutil.virtual_memory().available) / 1e9
    except Exception:
        pass
    try:
        inv = json.loads((ROOT / "reports" / "frontier_program"
                          / "hardware_inventory.json").read_text(encoding="utf-8"))
        return float(inv["memory"].get("available_bytes", 0)) / 1e9
    except Exception:
        return 0.0


def main() -> int:
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        ngpu = int(torch.cuda.device_count()) if cuda else 0
    except Exception:
        cuda, ngpu = False, 0
    free_ram = _free_ram_gb()

    models = ["hercule_lm_nano", "hercule_lm_micro", "hercule_lm_s10m",
              "hercule_lm_100m", "hercule-lm-300m", "hercule-lm-1b",
              "hercule-lm-3b", "hercule-lm-7b"]
    rows = []
    for name in models:
        cfg = load_config(name)
        params = cfg.parameter_count()
        mem = estimate_memory(params, 8, cfg.context_length // 2,
                              cfg.hidden_size, cfg.num_layers,
                              cfg.num_heads, cfg.vocab_size)
        train_gb = mem["total_training_mb"] / 1000.0
        if cfg.model_id in MEASURED_CPU_TOKS:
            toks, ev = MEASURED_CPU_TOKS[cfg.model_id], "MEASURED_CPU"
        else:
            toks, ev = projected_cpu_toks(params), "ESTIMATED"
        target = params * 20  # chinchilla-style 20 tok/param
        try:
            eta = estimate_time(toks, target)
            days = eta["days"]
        except Exception:
            days = None
        # Feasibility on THIS box (live free-RAM probe).
        if train_gb > free_ram and not cuda:
            verdict, why = "BLOCKED", f"needs ~{train_gb:.1f}GB, box has ~{free_ram:.1f}GB free"
        elif not cuda and params > 60_000_000:
            verdict, why = "BLOCKED", "too slow on CPU + RAM constrained"
        elif cuda:
            verdict, why = "READY", "CUDA present (re-run for MEASURED_CUDA)"
        else:
            verdict, why = "READY", "fits current RAM"
        rows.append({
            "model": cfg.model_id, "params": params,
            "arch_hash": cfg.architecture_hash(),
            "train_mem_gb_est": round(train_gb, 2),
            "toks": round(toks, 1), "toks_evidence": ev,
            "target_tokens": target,
            "eta_days": days, "eta_evidence": ev,
            "cuda_toks": "NOT_RUN", "verdict": verdict, "reason": why,
        })
        print(f"{cfg.model_id:18s} {params:>12,} params "
              f"mem~{train_gb:6.1f}GB tok/s={toks:7.1f}({ev}) "
              f"eta={days}d -> {verdict} ({why})")

    out = ROOT / "reports" / "frontier_program"
    out.mkdir(parents=True, exist_ok=True)
    (out / "feasibility.json").write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cuda_available": cuda, "gpu_count": ngpu,
        "free_ram_gb": round(free_ram, 2),
        "measured_cpu_reference": MEASURED_CPU_TOKS,
        "models": rows,
        "note": "ESTIMATED rows project from MEASURED_CPU via param scaling; "
                "CUDA rows are NOT_RUN until a GPU benchmark executes.",
    }, indent=1), encoding="utf-8")
    print("feasibility written to reports/frontier_program/feasibility.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
