from __future__ import annotations
"""Checkpoint registry with explicit acceptance gate (spec §12).

Downloaded experiment checkpoints NEVER replace the approved model
automatically. Adoption requires adopt() with an explicit reason +
measured eval evidence. Previous checkpoints are preserved.
"""

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY = "artifacts/kaggle_runs/CHECKPOINT_REGISTRY.json"


def _load() -> List[Dict[str, Any]]:
    try:
        return list(json.loads(Path(REGISTRY).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def _save(rows: List[Dict[str, Any]]) -> None:
    Path(REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(REGISTRY) + ".tmp")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    tmp.replace(REGISTRY)


def register(run_id: str, checkpoint_path: str, eval_result: Dict[str, Any]) -> Dict[str, Any]:
    rows = _load()
    entry = {"run_id": run_id, "checkpoint": checkpoint_path,
             "eval": dict(eval_result), "approved": False}
    rows.append(entry)
    _save(rows)
    return entry


def adopt(run_id: str, reason: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Explicit acceptance gate. Requires measured improvement evidence."""
    if not reason or not evidence:
        raise ValueError("ADOPT_REFUSED: reason + measured evidence required")
    rows = _load()
    for row in rows:
        if row["run_id"] == run_id:
            row["approved"] = True
            row["adopt_reason"] = reason
            row["adopt_evidence"] = dict(evidence)
            _save(rows)
            return row
    raise ValueError(f"ADOPT_REFUSED: unknown run {run_id!r}")


def approved() -> Optional[Dict[str, Any]]:
    rows = [r for r in _load() if r.get("approved")]
    return rows[-1] if rows else None
