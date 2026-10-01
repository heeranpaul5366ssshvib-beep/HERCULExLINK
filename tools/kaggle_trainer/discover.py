from __future__ import annotations
"""Project discovery (spec §1): repo root, components, config, backends."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REQUIRED = ["models/hercule_lm", "training", "evaluation", "scripts"]


def find_root(start: str = "") -> Path:
    cur = Path(start or Path.cwd()).resolve()
    for _ in range(8):
        if (cur / "models" / "hercule_lm" / "train.py").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise RuntimeError("HERCULE repository root not found (no models/hercule_lm/train.py)")


def inventory(root: str = "") -> Dict[str, Any]:
    base = Path(root) if root else find_root()
    parts = {}
    for rel in list(REQUIRED) + ["models/hercule_lm/configs",
                                 "training/checkpoints", "training/data",
                                 "tools/kaggle_trainer"]:
        parts[rel] = "present" if (base / rel).exists() else "MISSING"
    configs = sorted(p.stem for p in (base / "models/hercule_lm/configs").glob("*.json")) \
        if (base / "models/hercule_lm/configs").exists() else []
    return {"root": str(base), "parts": parts, "configs": configs}


def backend_capability() -> Dict[str, Any]:
    """Local backend probe (informational: local never trains large jobs)."""
    out: Dict[str, Any] = {"numpy": False, "torch": False,
                           "torch_cuda": False, "torch_version": None}
    try:
        import numpy  # noqa: F401

        out["numpy"] = True
    except Exception:
        pass
    try:
        import torch

        out["torch"] = True
        out["torch_version"] = getattr(torch, "__version__", "?")
        out["torch_cuda"] = bool(torch.cuda.is_available())
    except Exception:
        pass
    return out


def active_config(root: str = "", name: str = "") -> Dict[str, Any]:
    base = Path(root) if root else find_root()
    sys.path.insert(0, str(base))
    from models.hercule_lm.config import load_config

    cfg = load_config(name or "hercule_lm_micro")
    return {"model_id": cfg.model_id, "params": cfg.parameter_count(),
            "arch_hash": cfg.architecture_hash(), "config": cfg.as_dict()}
