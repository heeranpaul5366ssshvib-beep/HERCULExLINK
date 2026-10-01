from __future__ import annotations
"""Evaluation bridge (spec §10): local reload + compat + eval + deltas.

Never fabricates improvements. Adoption of a new checkpoint requires
an explicit acceptance gate (see checkpoints.py).
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def verify_checkpoint(checkpoint_dir: str, tokenizer_dir: str = "") -> Dict[str, Any]:
    """Reload checkpoint locally; check arch/tokenizer/dataset identity."""
    manifest = json.loads((Path(checkpoint_dir) / "manifest.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(Path.cwd()))
    from models.hercule_lm.config import HerculeLMConfig
    from models.hercule_lm.torch_model import TorchHerculeLM
    from models.hercule_lm import checkpoint as ckpt

    cfg = HerculeLMConfig.from_dict(manifest["architecture"])
    model = TorchHerculeLM(cfg, seed=0)
    loaded = ckpt.load_torch_checkpoint(checkpoint_dir, model, strict=True, map_to="cpu")
    out = {"reload_ok": True, "arch_hash": manifest.get("architecture_hash"),
           "params": manifest.get("parameter_count"),
           "tokenizer_checksum": (manifest.get("tokenizer") or {}).get("checksum"),
           "dataset_hash": (manifest.get("dataset") or {}).get("dataset_hash"),
           "source": (loaded.get("_load") or {}).get("source_format", "?")}
    if tokenizer_dir:
        from models.hercule_lm.tokenizer import HerculeBPETokenizer

        tok = HerculeBPETokenizer.load(tokenizer_dir)
        out["tokenizer_compat"] = (tok.checksum() == out["tokenizer_checksum"])
    return out


def run_eval(checkpoint_dir: str, tokenizer_dir: str,
             suites: List[str] | None = None) -> Dict[str, Any]:
    """CPU eval of a downloaded checkpoint on harness suites."""
    sys.path.insert(0, str(Path.cwd()))
    from models.hercule_lm.config import HerculeLMConfig
    from models.hercule_lm.eval_harness import model_predict_factory, run_all
    from models.hercule_lm.tokenizer import HerculeBPETokenizer
    from models.hercule_lm.torch_model import TorchHerculeLM
    from models.hercule_lm import checkpoint as ckpt

    manifest = json.loads((Path(checkpoint_dir) / "manifest.json").read_text(encoding="utf-8"))
    cfg = HerculeLMConfig.from_dict(manifest["architecture"])
    tok = HerculeBPETokenizer.load(tokenizer_dir)
    model = TorchHerculeLM(cfg, seed=0)
    ckpt.load_torch_checkpoint(checkpoint_dir, model, strict=True, map_to="cpu")
    suites = suites or ["MATH", "STRUCTURED_OUTPUT", "GENERAL"]
    rep = run_all(model_predict_factory(model, tok, max_new_tokens=16),
                  model_id=manifest.get("model_id", "?"),
                  checkpoint=checkpoint_dir, suites=suites)
    return {s: rep["suites"][s]["mean"] for s in suites}


def deltas(new_scores: Dict[str, float],
           old_scores: Dict[str, float]) -> Dict[str, Any]:
    """Per-suite verdicts vs a previous checkpoint (measured only)."""
    out: Dict[str, Any] = {}
    for suite, score in new_scores.items():
        old = old_scores.get(suite)
        if old is None:
            out[suite] = "NOT_COMPARABLE"
        elif score - old > 1e-9:
            out[suite] = "IMPROVED"
        elif old - score > 1e-9:
            out[suite] = "REGRESSED"
        else:
            out[suite] = "UNCHANGED"
    return out
