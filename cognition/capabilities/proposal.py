from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Capability Proposal Contract
Author: Heeran Paul
License: MIT
--------------------------------------------

Typed contract for proposed capabilities. Proposals are data: they
carry a name, confidence, source, and rationale — but grant nothing.
Only the deterministic validator (registry + policy) can turn a
proposal into an executable requirement.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ProposalSource(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC_MODEL = "semantic_model"
    EXPLICIT_USER = "explicit_user"
    SYSTEM_RULE = "system_rule"
    PLUGIN = "plugin"
    OTHER = "other"


class ProposalError(RuntimeError):
    """Structured proposal failure with a machine-readable code."""

    def __init__(self, message: str, code: str = "INVALID_PROPOSAL"):
        super().__init__(message)
        self.code = code


@dataclass
class CapabilityProposal:
    """One proposed capability (proposal, not authorization)."""

    name: str
    confidence: float = 1.0
    source: ProposalSource = ProposalSource.KEYWORD
    explanation: str = ""
    required: bool = True
    condition: str = ""
    depends_on: List[str] = field(default_factory=list)
    known: bool = True  # False when the name is not in the registry
    model_metadata: Dict[str, Any] = field(default_factory=dict)
    rejection: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "confidence": round(float(self.confidence), 3),
            "source": self.source.value,
            "explanation": self.explanation,
            "required": bool(self.required),
            "condition": self.condition,
            "depends_on": list(self.depends_on),
            "known": self.known,
            "model_metadata": dict(self.model_metadata),
            "rejection": dict(self.rejection),
        }


def _parse_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        raise ProposalError(f"invalid confidence: {value!r}", "INVALID_PROPOSAL")
    if not 0.0 <= confidence <= 1.0:
        raise ProposalError(f"confidence out of range: {value!r}", "INVALID_PROPOSAL")
    return confidence


def parse_proposal_entry(entry: Any, source: ProposalSource = ProposalSource.SEMANTIC_MODEL) -> CapabilityProposal:
    """Strictly parse one model-proposed entry. Unknown fields are
    ignored with a warning; invalid types/names/confidence reject the
    entry loudly (never silently fixed)."""
    warnings: List[str] = []
    if not isinstance(entry, dict):
        raise ProposalError(f"proposal entry must be an object, got {type(entry).__name__}", "INVALID_PROPOSAL")
    known_fields = {"name", "confidence", "reason", "explanation", "required", "optional",
                    "condition", "depends_on", "model", "model_id"}
    for key in entry:
        if key not in known_fields:
            warnings.append(f"unknown field ignored: {key}")
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ProposalError(f"invalid capability name: {name!r}", "INVALID_PROPOSAL")
    required = entry.get("required", not entry.get("optional", False))
    if not isinstance(required, bool):
        raise ProposalError(f"invalid required flag: {required!r}", "INVALID_PROPOSAL")
    depends_on = entry.get("depends_on", [])
    if not isinstance(depends_on, list) or any(not isinstance(d, str) for d in depends_on):
        raise ProposalError(f"invalid depends_on: {depends_on!r}", "INVALID_PROPOSAL")
    condition = entry.get("condition", "")
    if not isinstance(condition, str):
        raise ProposalError(f"invalid condition: {condition!r}", "INVALID_PROPOSAL")
    proposal = CapabilityProposal(
        name=str(name).strip().upper(),
        confidence=_parse_confidence(entry.get("confidence", 0.5)),
        source=source,
        explanation=str(entry.get("reason", entry.get("explanation", ""))),
        required=required,
        condition=condition.strip(),
        depends_on=[str(d).strip().upper() for d in depends_on],
    )
    proposal.model_metadata["warnings"] = warnings
    return proposal


def parse_proposal_payload(payload: Any) -> Tuple[List[CapabilityProposal], List[str], List[str]]:
    """Parse raw model output into (proposals, warnings, errors).

    Accepts a dict, a list, or a JSON string (with a JSON block
    extracted when wrapped in prose). Malformed payloads yield errors,
    never exceptions — the caller falls back deterministically.
    """
    warnings: List[str] = []
    errors: List[str] = []
    proposals: List[CapabilityProposal] = []
    data = payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except Exception:
            start, end = payload.find("{"), payload.rfind("}")
            if start < 0 or end <= start:
                return [], warnings, [f"SEMANTIC_MALFORMED: no JSON object in output"]
            try:
                data = json.loads(payload[start:end + 1])
            except Exception as exc:
                return [], warnings, [f"SEMANTIC_MALFORMED: {exc}"[:200]]
    entries: List[Any] = []
    if isinstance(data, dict):
        for key in ("capabilities", "proposals", "items"):
            if isinstance(data.get(key), list):
                entries = data[key]
                break
        else:
            return [], warnings, ["SEMANTIC_MALFORMED: no capabilities list found"]
        for key in data:
            if key not in ("capabilities", "proposals", "items"):
                warnings.append(f"unknown top-level field ignored: {key}")
    elif isinstance(data, list):
        entries = data
    else:
        return [], warnings, [f"SEMANTIC_MALFORMED: unexpected payload type {type(data).__name__}"]
    seen: Dict[str, CapabilityProposal] = {}
    for entry in entries:
        try:
            proposal = parse_proposal_entry(entry)
        except ProposalError as exc:
            errors.append(f"{exc.code}: {exc}")
            continue
        warnings.extend(proposal.model_metadata.pop("warnings", []))
        if proposal.name in seen:
            # Duplicate entries merge: keep the higher-confidence one and
            # require the capability if either copy requires it.
            existing = seen[proposal.name]
            existing.confidence = max(existing.confidence, proposal.confidence)
            existing.required = existing.required or proposal.required
            existing.depends_on = sorted(set(existing.depends_on) | set(proposal.depends_on))
            if proposal.condition and proposal.condition not in (existing.condition or ""):
                existing.condition = (existing.condition + "; " + proposal.condition).strip("; ")
            warnings.append(f"duplicate entry merged: {proposal.name}")
        else:
            seen[proposal.name] = proposal
            proposals.append(proposal)
    return proposals, warnings, errors
