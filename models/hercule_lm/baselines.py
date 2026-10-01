from __future__ import annotations
"""Benchmark baseline database (Phase 6P): improved/unchanged/regressed.

Append-only JSON store of suite means per (model, checkpoint,
benchmark). Comparison requires the same benchmark version and the
same suite set, else "not-comparable" — never silently compared.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_PATH = "reports/frontier_program/baselines.json"
TOL = 1e-9


def _load(path: str) -> List[Dict[str, Any]]:
    try:
        return list(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def record(entry: Dict[str, Any], path: str = DEFAULT_PATH) -> str:
    """Append one eval record {model, checkpoint, benchmark, suites{...}}."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _load(path)
    rows.append(dict(entry))
    tmp = target.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    tmp.replace(target)
    return str(target)


def compare(new: Dict[str, Any], old: Dict[str, Any]) -> Dict[str, Any]:
    """Per-suite verdicts between two records."""
    if new.get("benchmark") != old.get("benchmark"):
        return {"status": "not-comparable",
                "reason": "benchmark version differs"}
    out: Dict[str, Any] = {}
    for suite, nmean in (new.get("suites") or {}).items():
        n = nmean["mean"] if isinstance(nmean, dict) else float(nmean)
        o = (old.get("suites") or {}).get(suite)
        o = o["mean"] if isinstance(o, dict) else o
        if o is None:
            out[suite] = "not-comparable"
        elif n - o > TOL:
            out[suite] = "improved"
        elif o - n > TOL:
            out[suite] = "regressed"
        else:
            out[suite] = "unchanged"
    return out


def latest_for(model: str, path: str = DEFAULT_PATH) -> Dict[str, Any] | None:
    rows = [r for r in _load(path) if r.get("model") == model]
    return rows[-1] if rows else None
