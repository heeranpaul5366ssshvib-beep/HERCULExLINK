from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Learning Engine
Author: Heeran Paul
License: MIT
--------------------------------------------

LEARNING consumes *evaluated experience* — never raw arbitrary state —
and produces validated learning proposals. Responsibility boundary:

KNOWLEDGE   -> KnowledgeManager  (world/reference material)
MEMORY      -> MemoryManager     (authorized interaction state)
EXPERIENCE  -> ExperienceManager (distilled task outcomes)
LEARNING    -> LearningEngine    (this module: proposals + validation)

Preferred flow: TASK -> RESULT -> VERIFICATION -> EXPERIENCE ->
EVALUATION -> LEARNING PROPOSAL -> VALIDATION -> PROMOTION.

Phase H migration: the orphan ``_knowledge`` key/value store (zero
production callers, duplicating SemanticMemory) is REMOVED. The legacy
KV methods remain as loud compatibility shims that raise an
informative error pointing at the new API — no second hidden
knowledge store is retained. See docs/phase-h/learning.md + ADR-005.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

_REMOVED_MESSAGE = (
    "LearningEngine KV store was removed in Phase H (orphaned silo, zero callers). "
    "Use ingest_evaluated()/propose()/validate()/promote(); "
    "see docs/phase-h/learning.md and docs/phase-g/learning-silo.md."
)


class ProposalKind(str, Enum):
    PROCEDURE_CANDIDATE = "procedure_candidate"
    RETRIEVAL_IMPROVEMENT = "retrieval_improvement"
    ROUTING_IMPROVEMENT = "routing_improvement"
    WORKFLOW_IMPROVEMENT = "workflow_improvement"
    KNOWLEDGE_CANDIDATE = "knowledge_candidate"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass
class LearningProposalRecord:
    proposal_id: str
    kind: ProposalKind
    source_experience_ids: List[str] = field(default_factory=list)
    rationale: str = ""
    expected_benefit: str = ""
    confidence: float = 0.5
    validation_requirements: List[str] = field(default_factory=list)
    status: ProposalStatus = ProposalStatus.PROPOSED
    created_at: str = ""
    decided_at: str = ""
    decision_note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind.value,
            "source_experience_ids": list(self.source_experience_ids),
            "rationale": self.rationale,
            "expected_benefit": self.expected_benefit,
            "confidence": self.confidence,
            "validation_requirements": list(self.validation_requirements),
            "status": self.status.value,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decision_note": self.decision_note,
        }

    def to_contract(self) -> Dict[str, Any]:
        """Convert to the ownership ``LearningProposal`` contract shape."""
        from cognition.contracts import LearningProposal

        return LearningProposal(
            source="learning-engine",
            proposal_type=self.kind.value,
            description=self.rationale,
            evidence=list(self.source_experience_ids),
            confidence=float(self.confidence),
            accepted=self.status == ProposalStatus.PROMOTED,
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningEngine:
    """Evaluated-experience intake, proposals, validation, promotion."""

    def __init__(
        self,
        experience_manager=None,
        min_support: int = 2,
        min_mean_success: float = 0.7,
        min_quality: float = 0.5,
    ):
        self.experience_manager = experience_manager
        self.min_support = min_support
        self.min_mean_success = min_mean_success
        self.min_quality = min_quality
        self._intake: Dict[str, Dict[str, Any]] = {}
        self._proposals: Dict[str, LearningProposalRecord] = {}

    # --------------------------------------------------
    # intake: evaluated experience only
    # --------------------------------------------------
    def ingest_evaluated(self, experience: Union[Dict[str, Any], Any], quality: Union[Dict[str, Any], float, Any]) -> Dict[str, Any]:
        """Accept one experience + its quality evaluation.

        Returns an intake receipt ``{"accepted", "experience_id",
        "reason"}``. Unevaluated input (missing success, verification,
        or quality score) is refused with a reason — never stored.
        """
        exp = experience.as_dict() if hasattr(experience, "as_dict") else dict(experience or {})
        if isinstance(quality, (int, float)):
            score = float(quality)
        elif hasattr(quality, "score"):
            score = float(quality.score)
        else:
            quality_d = dict(quality or {})
            score = quality_d.get("score", quality_d.get("quality"))
        exp_id = str(exp.get("experience_id", ""))
        missing = []
        if exp.get("success") is None:
            missing.append("success")
        if not exp.get("verification"):
            missing.append("verification")
        if score is None:
            missing.append("quality score")
        if not exp_id or missing:
            return {"accepted": False, "experience_id": exp_id, "reason": f"missing evaluated evidence: {missing or ['experience_id']}"}
        self._intake[exp_id] = {"experience": exp, "quality_score": float(score)}
        return {"accepted": True, "experience_id": exp_id, "reason": ""}

    # --------------------------------------------------
    # proposals
    # --------------------------------------------------
    def propose(
        self,
        kind: Union[ProposalKind, str],
        source_experience_ids: List[str],
        rationale: str,
        expected_benefit: str = "",
        confidence: float = 0.5,
        validation_requirements: Optional[List[str]] = None,
    ) -> LearningProposalRecord:
        kind = ProposalKind(kind)
        unknown = [eid for eid in source_experience_ids if eid not in self._intake]
        if unknown:
            raise ValueError(f"proposal sources not ingested as evaluated experience: {unknown}")
        if not rationale:
            raise ValueError("proposal rationale must not be empty")
        record = LearningProposalRecord(
            proposal_id=f"lp-{len(self._proposals) + 1}",
            kind=kind,
            source_experience_ids=list(source_experience_ids),
            rationale=rationale,
            expected_benefit=expected_benefit,
            confidence=max(0.0, min(1.0, float(confidence))),
            validation_requirements=list(validation_requirements or ["support threshold", "quality threshold"]),
            created_at=_utc_now_iso(),
        )
        self._proposals[record.proposal_id] = record
        return record

    def propose_from_experiences(
        self,
        kind: Union[ProposalKind, str],
        experiences: List[Union[Dict[str, Any], Any]],
        rationale: str,
        expected_benefit: str = "",
    ) -> LearningProposalRecord:
        """Build a proposal from experiences, deriving confidence."""
        ids = []
        for exp in experiences:
            data = exp.as_dict() if hasattr(exp, "as_dict") else dict(exp or {})
            ids.append(str(data.get("experience_id", "")))
        ingested = [self._intake[eid] for eid in ids if eid in self._intake]
        mean_success = (
            sum(float(v["experience"].get("success", 0.0)) for v in ingested) / len(ingested) if ingested else 0.0
        )
        return self.propose(kind, [eid for eid in ids if eid in self._intake], rationale, expected_benefit, confidence=mean_success)

    # --------------------------------------------------
    # validation -> promotion / rejection
    # --------------------------------------------------
    def _evidence(self, record: LearningProposalRecord) -> Dict[str, Any]:
        entries = [self._intake[eid] for eid in record.source_experience_ids if eid in self._intake]
        successes = [float(e["experience"].get("success", 0.0)) for e in entries]
        qualities = [float(e["quality_score"]) for e in entries]
        return {
            "support": len(entries),
            "mean_success": sum(successes) / len(successes) if successes else 0.0,
            "min_quality": min(qualities) if qualities else 0.0,
        }

    def validate(self, proposal_id: str) -> LearningProposalRecord:
        """Check evidence thresholds; VALIDATED or stays PROPOSED."""
        record = self._proposals.get(proposal_id)
        if record is None:
            raise KeyError(f"unknown learning proposal: {proposal_id}")
        if record.status != ProposalStatus.PROPOSED:
            return record
        evidence = self._evidence(record)
        failures = []
        if evidence["support"] < self.min_support:
            failures.append(f"support {evidence['support']} < {self.min_support}")
        if evidence["mean_success"] < self.min_mean_success:
            failures.append(f"mean success {evidence['mean_success']:.2f} < {self.min_mean_success}")
        if evidence["min_quality"] < self.min_quality:
            failures.append(f"min quality {evidence['min_quality']:.2f} < {self.min_quality}")
        if failures:
            record.decision_note = "validation deferred: " + "; ".join(failures)
        else:
            record.status = ProposalStatus.VALIDATED
            record.decided_at = _utc_now_iso()
            record.decision_note = (
                f"validated: support={evidence['support']} "
                f"mean_success={evidence['mean_success']:.2f} min_quality={evidence['min_quality']:.2f}"
            )
        return record

    def promote(self, proposal_id: str, approver: str = "") -> LearningProposalRecord:
        """Promote a VALIDATED proposal to trusted. Requires approval."""
        record = self._proposals.get(proposal_id)
        if record is None:
            raise KeyError(f"unknown learning proposal: {proposal_id}")
        if record.status != ProposalStatus.VALIDATED:
            raise ValueError(f"only VALIDATED proposals promote (now {record.status.value})")
        record.status = ProposalStatus.PROMOTED
        record.decided_at = _utc_now_iso()
        record.decision_note = f"promoted by {approver or 'review'}"
        return record

    def reject(self, proposal_id: str, reason: str = "") -> LearningProposalRecord:
        record = self._proposals.get(proposal_id)
        if record is None:
            raise KeyError(f"unknown learning proposal: {proposal_id}")
        if record.status == ProposalStatus.PROMOTED:
            raise ValueError("promoted proposals cannot be rejected; supersede instead")
        record.status = ProposalStatus.REJECTED
        record.decided_at = _utc_now_iso()
        record.decision_note = reason or "rejected"
        return record

    # --------------------------------------------------
    # queries
    # --------------------------------------------------
    def get(self, proposal_id: str) -> Optional[LearningProposalRecord]:
        return self._proposals.get(proposal_id)

    def proposals(self, status: Optional[Union[ProposalStatus, str]] = None) -> List[LearningProposalRecord]:
        items = list(self._proposals.values())
        if status is not None:
            status = ProposalStatus(status)
            items = [p for p in items if p.status == status]
        return items

    def intake_ids(self) -> List[str]:
        return sorted(self._intake)

    def statistics(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for record in self._proposals.values():
            by_status[record.status.value] = by_status.get(record.status.value, 0) + 1
        return {"intake": len(self._intake), "proposals": len(self._proposals), "by_status": by_status}

    # --------------------------------------------------
    # removed KV silo: loud compatibility shims (no hidden store)
    # --------------------------------------------------
    def learn(self, key: str, value: Any):
        raise RuntimeError(_REMOVED_MESSAGE)

    def recall(self, key: str):
        raise RuntimeError(_REMOVED_MESSAGE)

    def update(self, key: str, value: Any):
        raise RuntimeError(_REMOVED_MESSAGE)

    def forget(self, key: str):
        raise RuntimeError(_REMOVED_MESSAGE)

    def all(self):
        raise RuntimeError(_REMOVED_MESSAGE)

    def clear(self):
        raise RuntimeError(_REMOVED_MESSAGE)
