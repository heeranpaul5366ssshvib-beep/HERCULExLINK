from __future__ import annotations
"""Offline improvement export (6U §11): validated examples for FUTURE training.

Collects {input, failure, diagnosis, better strategy, verified result}
from consolidated lessons + recovered traces. Output matches the Phase-6
postdata sample schema so it can feed SFT/preference pipelines LATER.
Ordinary execution NEVER trains on this; it only appends the file.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def to_postdata_sample(record: Dict[str, Any]) -> Dict[str, Any]:
    failure = record.get("failure", {})
    prompt = (f"Task: {record.get('goal', '')}\nAttempt: "
              f"{failure.get('attempted_action', '')}\nObservation: "
              f"{failure.get('observation', '')}\nDiagnose and revise.")
    response = (f"Diagnosis ({record.get('diagnosis_grade', '')}): "
                f"{record.get('diagnosis', '')}\nRevised strategy: "
                f"{record.get('better_strategy', '')}\nVerified: "
                f"{record.get('verified_result', '')}")
    rid = hashlib.sha256(f"{prompt}\x00{response}".encode()).hexdigest()[:16]
    return {"id": rid, "task": "reasoning", "language": "english",
            "source": "hercule-adaptive-export-v1",
            "license": "HERCULE-authored (MIT, repo)",
            "version": "adaptive-export-v1", "split": "train",
            "prompt": prompt, "response": response,
            "validated": bool(record.get("verified")),
            "contaminated": False}


def export_validated(traces: List[Dict[str, Any]], path: str) -> Dict[str, Any]:
    """Export recovered+verified traces only. Returns a manifest."""
    samples = []
    for trace in traces:
        if not (trace.get("recovered") and trace.get("verified")
                and trace.get("lesson")):
            continue
        lesson = trace["lesson"]
        attempts = trace.get("attempts", [])
        first = attempts[0] if attempts else {}
        last = attempts[-1] if attempts else {}
        samples.append(to_postdata_sample({
            "goal": trace.get("goal", ""),
            "failure": {"attempted_action": first.get("action", ""),
                        "observation": first.get("observation", "")},
            "diagnosis": lesson.get("statement", ""),
            "diagnosis_grade": "LIKELY",
            "better_strategy": last.get("action", ""),
            "verified_result": last.get("observation", ""),
            "verified": True}))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.json")
    tmp.write_text(json.dumps({"version": "adaptive-export-v1",
                               "samples": samples}, indent=1), encoding="utf-8")
    tmp.replace(target)
    return {"path": str(target), "samples": len(samples)}
