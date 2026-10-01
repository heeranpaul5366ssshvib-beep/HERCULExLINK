from __future__ import annotations
"""Self-diagnosis (6U §2): WHAT/WHY/WHAT-ASSUMPTION/WHAT-MISSING/WHAT-CHANGES.

Diagnoses are evidence-graded:
- CONFIRMED: direct observation entails the cause (e.g. schema error
  names the bad argument; retry with fix succeeds).
- LIKELY: strong but indirect evidence.
- UNCERTAIN: insufficient evidence — durable changes forbidden.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from cognition.adaptation.failures import FailureRecord, FailureType

CONFIRMED = "CONFIRMED"
LIKELY = "LIKELY"
UNCERTAIN = "UNCERTAIN"


@dataclass
class Diagnosis:
    what_failed: str = ""
    why: str = ""
    wrong_assumption: str = ""
    missing_information: str = ""
    should_change: str = ""
    must_not_change: str = ""
    grade: str = UNCERTAIN
    confidence: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def actionable(self) -> bool:
        """Only CONFIRMED/LIKELY diagnoses may drive durable changes."""
        return self.grade in (CONFIRMED, LIKELY) and bool(self.should_change)


_REVISION_HINTS = {
    FailureType.INVALID_ARGUMENT.value: "different arguments",
    FailureType.TOOL_ERROR.value: "different tool or arguments",
    FailureType.ENVIRONMENT_CHANGE.value: "additional information gathering",
    FailureType.PLANNING_ERROR.value: "different ordering",
    FailureType.STATE_MISREAD.value: "additional verification step",
    FailureType.VERIFICATION_FAILURE.value: "additional verification step",
    FailureType.WRONG_ASSUMPTION.value: "different reasoning path",
    FailureType.TIMEOUT.value: "smaller task decomposition",
    FailureType.DATA_ERROR.value: "additional information gathering",
}


def diagnose(record: FailureRecord,
             extra_evidence: Dict[str, Any] | None = None) -> Diagnosis:
    """Derive a graded diagnosis from a failure record + evidence."""
    extra = dict(extra_evidence or {})
    obs = (record.observation or "").strip()
    diag = Diagnosis(
        what_failed=f"{record.tool or 'action'}:{record.attempted_action or record.step_id}",
        must_not_change="safety policy, permissions, autonomy limits, model weights",
    )
    ftype = record.failure_type
    if ftype == FailureType.INVALID_ARGUMENT.value:
        diag.why = f"tool rejected arguments: {obs[:200]}"
        diag.wrong_assumption = "assumed argument schema was correct"
        diag.missing_information = "tool's accepted schema"
        diag.should_change = _REVISION_HINTS[ftype]
        diag.grade = CONFIRMED if obs else LIKELY
        diag.confidence = 0.9 if obs else 0.65
    elif ftype == FailureType.PERMISSION_DENIED.value:
        diag.why = "policy denied the action"
        diag.wrong_assumption = "assumed the action was permitted"
        diag.missing_information = "required approval or grant"
        diag.should_change = "request approval or use a permitted alternative"
        diag.grade = CONFIRMED
        diag.confidence = 0.95
    elif ftype == FailureType.TIMEOUT.value:
        diag.why = "action exceeded its time budget"
        diag.wrong_assumption = "assumed the action would finish in budget"
        diag.missing_information = "actual cost / progress signal"
        diag.should_change = _REVISION_HINTS[ftype]
        diag.grade = LIKELY
        diag.confidence = 0.7
    elif ftype in (FailureType.TOOL_ERROR.value,
                   FailureType.ENVIRONMENT_CHANGE.value):
        diag.why = record.failure_reason or "tool/environment error"
        diag.wrong_assumption = "assumed environment matched expectation"
        diag.missing_information = "current environment state"
        diag.should_change = _REVISION_HINTS.get(ftype, "different tool or arguments")
        diag.grade = LIKELY if record.confidence >= 0.6 else UNCERTAIN
        diag.confidence = round(min(0.75, record.confidence), 2)
    elif ftype == FailureType.VERIFICATION_FAILURE.value:
        diag.why = "output did not match expectation"
        diag.wrong_assumption = "assumed first attempt was correct"
        diag.missing_information = "correct derivation or data"
        diag.should_change = _REVISION_HINTS[ftype]
        diag.grade = LIKELY
        diag.confidence = 0.6
    else:
        diag.why = "cause not determinable from available evidence"
        diag.wrong_assumption = ""
        diag.missing_information = "diagnostic observation"
        diag.should_change = ""
        diag.grade = UNCERTAIN
        diag.confidence = round(min(0.3, record.confidence), 2)
    if extra.get("retry_with_fix_succeeded") and diag.should_change:
        diag.grade = CONFIRMED
        diag.confidence = max(diag.confidence, 0.9)
    return diag


def revision_for(diagnosis: Diagnosis, failed_action: Dict[str, Any],
                 alternatives: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Build a revised action that differs from the failed one.

    Never returns an identical repeat unless ``new_evidence`` is set.
    """
    alternatives = list(alternatives or [])
    for alt in alternatives:
        if _sig(alt) != _sig(failed_action):
            return {"action": alt, "reason": diagnosis.should_change,
                    "from_diagnosis": diagnosis.grade}
    mutated = dict(failed_action)
    mutated["retry_of"] = failed_action.get("step_id", "")
    mutated["revision_note"] = diagnosis.should_change or "retry with verification"
    mutated["verify"] = True
    return {"action": mutated, "reason": diagnosis.should_change,
            "from_diagnosis": diagnosis.grade}


def _sig(action: Dict[str, Any]) -> str:
    import json

    core = {k: action.get(k) for k in ("tool", "action", "input")}
    return json.dumps(core, sort_keys=True, default=str)
