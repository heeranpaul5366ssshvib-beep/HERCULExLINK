"""Phase H-B: LearningEngine migration — evaluated intake, proposals, validation."""

import pytest

from cognition.contracts import LearningProposal as ContractProposal
from cognition.experience.experience_manager import ExperienceManager
from cognition.learning.learning_manager import (
    LearningEngine,
    ProposalKind,
    ProposalStatus,
)
from cognition.task_manager.task_manager import TaskManager
from evaluation.metrics import compute_task_quality
from system.observability.trace import Tracer, trace_learning


_pair_counter = [0]


def _evaluated_pair(description="Diagnose router fault", result="fixed"):
    _pair_counter[0] += 1
    tasks = TaskManager()
    tid = tasks.create_task(description, task_id=f"phase-h-task-{_pair_counter[0]}")
    tasks.queue_task(tid)
    tasks.start(tid)
    tasks.complete(tid, result=result)
    task = tasks.get(tid)
    experience = ExperienceManager().record_from_task(task)
    experience.experience_id = f"phase-h-exp-{_pair_counter[0]}"
    quality = compute_task_quality(task).as_dict()
    return experience.as_dict(), quality


def test_intake_accepts_evaluated_rejects_raw():
    engine = LearningEngine()
    experience, quality = _evaluated_pair()
    receipt = engine.ingest_evaluated(experience, quality)
    assert receipt == {"accepted": True, "experience_id": experience["experience_id"], "reason": ""}
    assert engine.intake_ids() == [experience["experience_id"]]
    refused = engine.ingest_evaluated({"experience_id": "raw-1", "description": "x"}, {})
    assert refused["accepted"] is False and "missing" in refused["reason"]
    assert "raw-1" not in engine.intake_ids()


def test_proposal_lifecycle_validate_promote_reject():
    engine = LearningEngine(min_support=2, min_mean_success=0.7, min_quality=0.5)
    exp1, q1 = _evaluated_pair("Diagnose router fault A")
    exp2, q2 = _evaluated_pair("Diagnose router fault B")
    engine.ingest_evaluated(exp1, q1)
    proposal = engine.propose(ProposalKind.PROCEDURE_CANDIDATE, [exp1["experience_id"]],
                              rationale="repeatable diagnostic flow", expected_benefit="faster triage",
                              confidence=0.8, validation_requirements=["support threshold"])
    assert proposal.status == ProposalStatus.PROPOSED
    engine.validate(proposal.proposal_id)  # only 1 supporter: stays proposed
    assert engine.get(proposal.proposal_id).status == ProposalStatus.PROPOSED
    with pytest.raises(ValueError):
        engine.promote(proposal.proposal_id)
    engine.ingest_evaluated(exp2, q2)
    proposal2 = engine.propose("routing_improvement", [exp1["experience_id"], exp2["experience_id"]],
                               rationale="prefer healthy adapters first", expected_benefit="fewer retries")
    engine.validate(proposal2.proposal_id)
    assert engine.get(proposal2.proposal_id).status == ProposalStatus.VALIDATED
    engine.promote(proposal2.proposal_id, approver="review-board")
    assert engine.get(proposal2.proposal_id).status == ProposalStatus.PROMOTED
    engine.reject(proposal.proposal_id, reason="insufficient support")
    assert engine.get(proposal.proposal_id).status == ProposalStatus.REJECTED
    with pytest.raises(ValueError):
        engine.reject(proposal2.proposal_id)  # promoted is final
    with pytest.raises(KeyError):
        engine.validate("lp-999")
    stats = engine.statistics()
    assert stats["intake"] == 2 and stats["by_status"]["promoted"] == 1
    assert len(engine.proposals(status="rejected")) == 1


def test_proposal_guards_and_contract_shape():
    engine = LearningEngine()
    with pytest.raises(ValueError):
        engine.propose("procedure_candidate", ["ghost"], rationale="x")
    exp, quality = _evaluated_pair()
    engine.ingest_evaluated(exp, quality)
    with pytest.raises(ValueError):
        engine.propose("procedure_candidate", [exp["experience_id"]], rationale="")
    record = engine.propose_from_experiences("workflow_improvement", [exp], rationale="batch checks")
    assert record.confidence == pytest.approx(1.0)
    contract = record.to_contract()
    assert isinstance(contract, ContractProposal)
    assert contract.proposal_type == "workflow_improvement" and contract.accepted is False


def test_legacy_kv_silo_is_gone_not_hidden():
    engine = LearningEngine()
    assert not hasattr(engine, "_knowledge")
    for call in (lambda: engine.learn("k", "v"), lambda: engine.recall("k"),
                 lambda: engine.update("k", "v"), lambda: engine.forget("k"),
                 engine.all, engine.clear):
        with pytest.raises(RuntimeError, match="removed in Phase H"):
            call()


def test_end_to_end_task_to_promotion_with_trace():
    tracer = Tracer()
    tasks = TaskManager()
    engine = LearningEngine(min_support=2)
    ids = []
    for label in ("Repair adapter fault A", "Repair adapter fault B"):
        tid = tasks.create_task(label)
        tasks.queue_task(tid)
        tasks.start(tid)
        tasks.complete(tid, result="repaired")
        task = tasks.get(tid)
        exp = ExperienceManager().record_from_task(task).as_dict()
        quality = compute_task_quality(task).as_dict()
        receipt = engine.ingest_evaluated(exp, quality)
        assert receipt["accepted"] is True
        ids.append(exp["experience_id"])
        trace_learning(tracer, "corr-learn", "intake", "", {"experience_id": exp["experience_id"]})
    proposal = engine.propose("procedure_candidate", ids, rationale="adapter repair flow",
                              expected_benefit="repeatable recovery")
    trace_learning(tracer, "corr-learn", "proposed", proposal.proposal_id, {})
    engine.validate(proposal.proposal_id)
    trace_learning(tracer, "corr-learn", "validated", proposal.proposal_id, {})
    engine.promote(proposal.proposal_id, approver="e2e")
    trace_learning(tracer, "corr-learn", "promoted", proposal.proposal_id, {})
    assert engine.get(proposal.proposal_id).status == ProposalStatus.PROMOTED
    assert proposal.to_contract().accepted is True
    stages = tracer.get("corr-learn").as_dict()["stages"]["learning"]
    assert [e["event"] for e in stages] == ["intake", "intake", "proposed", "validated", "promoted"]
    assert trace_learning(None, "x", "intake")["event"] == "intake"
