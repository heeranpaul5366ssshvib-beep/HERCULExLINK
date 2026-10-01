from __future__ import annotations
"""Artifact return: download, verify, FINAL_REPORT.md (spec §9)."""

import json
from pathlib import Path
from typing import Any, Dict, List

from tools.kaggle_trainer import kaggle_executor as _kx
from tools.kaggle_trainer import manifest as _man


def run_dir(root: str = "", run_id: str = "") -> Path:
    base = Path(root) if root else Path("artifacts/kaggle_runs")
    target = base / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def download(kernel_id: str, dest: str) -> Dict[str, Any]:
    res = _kx.kernels_output(kernel_id, dest)
    files = sorted(str(p.relative_to(dest)) for p in Path(dest).rglob("*") if p.is_file())
    return {"returncode": res["returncode"], "tail": res["tail"], "files": files}


def verify_run(dest: str) -> Dict[str, Any]:
    """Check expected outputs exist + REMOTE_STATUS parseable."""
    base = Path(dest)
    checks = {
        "run.log": (base / "run.log").exists(),
        "REMOTE_STATUS.json": (base / "REMOTE_STATUS.json").exists(),
        "smoke.json": (base / "smoke.json").exists(),
        "gpu.json": (base / "gpu.json").exists(),
    }
    status: Dict[str, Any] = {}
    try:
        status = json.loads((base / "REMOTE_STATUS.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        checks["REMOTE_STATUS.json"] = f"unparseable: {exc}"
    return {"checks": checks, "status": status,
            "ok": all(v is True for v in checks.values())}


def write_final_report(dest: str, record: Dict[str, Any]) -> str:
    base = Path(dest)
    lines = [f"# Kaggle run {record.get('run_id', '?')}", ""]
    lines.append(f"Status: {record.get('status', '?')}")
    lines.append(f"GPU: {record.get('gpu', '?')}")
    lines.append(f"Steps: {record.get('steps_completed', '?')}")
    lines.append(f"Train loss: {record.get('train_loss', '?')}")
    lines.append(f"Valid loss: {record.get('validation_loss', '?')}")
    lines.append(f"Tok/s: {record.get('tokens_per_second', '?')}")
    lines.append(f"Checkpoint: {record.get('checkpoint_path', '?')}")
    lines.append(f"Evaluation: {json.dumps(record.get('evaluation_result', {}))}")
    if record.get("failure_reason"):
        lines.append(f"Failure: {record['failure_reason']}")
    lines.append("")
    lines.append("## Evidence classes")
    lines.append("All GPU rows MEASURED from remote telemetry or BLOCKED. "
                 "No local-CPU numbers presented as GPU results.")
    target = base / "FINAL_REPORT.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    (base / "RESULT.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return str(target)
