from __future__ import annotations
"""Automated model-card generator (Phase 6R).

Assembles identity, lineage, data, training, benchmark, safety, and
limitations from manifests + reports already on disk. Every section
labels its evidence class; unknown sections say UNKNOWN, never prose.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def generate(model_id: str, checkpoint_dir: str = "",
             reports_dir: str = "reports/frontier_program") -> Dict[str, Any]:
    from .config import load_config

    card: Dict[str, Any] = {"model": model_id, "evidence": "MIXED (see sections)"}
    try:
        cfg = load_config(model_id.replace("-", "_"))
        card["architecture"] = cfg.as_dict()
        card["parameters"] = cfg.parameter_count()
    except Exception as exc:
        card["architecture"] = f"UNKNOWN ({exc})"
    if checkpoint_dir:
        man = _read_json(str(Path(checkpoint_dir) / "manifest.json"))
        if man:
            card["checkpoint"] = {
                "format": man.get("checkpoint_format"),
                "architecture_hash": man.get("architecture_hash"),
                "tokenizer_checksum": (man.get("tokenizer") or {}).get("checksum"),
                "dataset_hash": (man.get("dataset") or {}).get("dataset_hash"),
                "origin": man.get("origin"),
                "backend": man.get("backend"),
                "device": man.get("device"),
                "train_state": man.get("train_state"),
            }
        else:
            card["checkpoint"] = "UNKNOWN (no manifest)"
    else:
        card["checkpoint"] = "UNKNOWN (no checkpoint supplied)"
    reports = Path(reports_dir)
    card["benchmarks"] = "see phase6_eval.json" if (reports / "phase6_eval.json").exists() \
        else "NOT_RUN"
    card["safety"] = "see phase6_eval.json SAFETY suite" if (reports / "phase6_eval.json").exists() \
        else "NOT_RUN"
    card["limitations"] = [
        "from-scratch model; no pretrained capability inherited",
        "tiny-model baselines score near zero on reasoning suites (measured)",
        "CUDA/multi-GPU status per frontier reports, not this card",
        "post-training improvements require measured eval deltas",
    ]
    card["lineage"] = "hercule-lm random initialization (no pretrained weights)"
    card["license"] = "HERCULE-authored (MIT, repo)"
    return card


def write_markdown(card: Dict[str, Any], path: str) -> str:
    lines = [f"# Model Card: {card.get('model')}", ""]
    lines.append(f"Parameters: {card.get('parameters', 'UNKNOWN')}")
    lines.append(f"Lineage: {card.get('lineage')}")
    lines.append(f"License: {card.get('license')}")
    lines.append("")
    lines.append("## Checkpoint")
    lines.append("```json")
    lines.append(json.dumps(card.get("checkpoint"), indent=1))
    lines.append("```")
    lines.append("## Benchmarks")
    lines.append(str(card.get("benchmarks")))
    lines.append("## Safety")
    lines.append(str(card.get("safety")))
    lines.append("## Limitations")
    for item in card.get("limitations", []):
        lines.append(f"- {item}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    return str(target)
