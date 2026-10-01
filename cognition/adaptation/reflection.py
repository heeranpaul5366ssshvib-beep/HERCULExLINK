from __future__ import annotations
"""Structured reflection output (6U §8) built on the existing engine.

Extends (never replaces) ReflectionEngine with the required schema:
failure / diagnosis / confidence / revision / validated /
promote_to_experience. Promotion requires validated=True AND an
actionable (CONFIRMED/LIKELY) diagnosis.
"""

from typing import Any, Dict


def structured_reflect(failure: Dict[str, Any], diagnosis: Dict[str, Any],
                       revision: Dict[str, Any], validated: bool,
                       engine=None) -> Dict[str, Any]:
    notes: list = []
    if engine is not None:
        try:
            base = engine.reflect(str(failure.get("observation", "")),
                                  str(revision.get("reason", "")))
            notes = list(base.get("notes", []))
        except Exception:
            notes = []
    confidence = float(diagnosis.get("confidence", 0.0))
    grade = str(diagnosis.get("grade", "UNCERTAIN"))
    promote = bool(validated) and grade in ("CONFIRMED", "LIKELY") \
        and bool(revision.get("reason"))
    return {"failure": str(failure.get("failure_type", "UNKNOWN")),
            "diagnosis": str(diagnosis.get("why", "")),
            "confidence": confidence, "grade": grade,
            "revision": str(revision.get("reason", "")),
            "validated": bool(validated),
            "promote_to_experience": promote,
            "notes": notes}
