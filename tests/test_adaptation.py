from __future__ import annotations
"""Test-time learning / mistake-driven adaptation tests (Phase 6U §18).

Covers: failure capture, classification, diagnosis, strategy revision,
retry, working-memory update, experience consolidation, skill
promotion, scope enforcement, stale invalidation, contradiction
handling, cross-task isolation, cross-user isolation, bounded retries,
A/B improvement, regression protection — plus the 11-step acceptance
demo (fail -> diagnose -> revise -> retry -> verify -> retain ->
reuse, unrelated tasks unaffected).
"""

import pytest

from cognition.adaptation import (AdaptiveExecutor, FailureType,
                                  classify_failure)
from cognition.adaptation.ab_eval import compare as ab_compare
from cognition.adaptation.diagnosis import diagnose, revision_for
from cognition.adaptation.env_learner import EnvironmentLearner
from cognition.adaptation.executor import action_signature
from cognition.adaptation.failures import build_record
from cognition.adaptation.lessons import LessonStore
from cognition.adaptation.metrics import LearningMetrics
from cognition.adaptation.offline_export import export_validated
from cognition.adaptation.reflection import structured_reflect
from cognition.adaptation.retry import RetryBudget, decide_retry
from cognition.adaptation.world_state import TaskStateLedger


# ---------- failure capture + classification ----------

def test_failure_capture_record_fields():
    rec = build_record("t1", "fetch data",
                       {"step_id": "s1", "action": "read", "tool": "files",
                        "input": {"path": "x"}, "plan": ["read"]},
                       "error: timeout after 5s", timed_out=True)
    d = rec.as_dict()
    assert d["task_id"] == "t1" and d["failure_type"] == "TIMEOUT"
    assert d["timestamp"] and d["environment_state_hash"]
    assert set(d) >= {"goal", "plan", "step_id", "attempted_action", "tool",
                      "input", "observation", "expected_result",
                      "actual_result", "failure_reason", "confidence",
                      "recovery_action", "retry_count", "final_outcome"}


def test_classification_types_and_unknown():
    assert classify_failure(error="invalid argument: foo")["type"] == "INVALID_ARGUMENT"
    assert classify_failure(error="traceback boom")["type"] == "TOOL_ERROR"
    assert classify_failure(error="permission denied")["type"] == "PERMISSION_DENIED"
    assert classify_failure(error="host unreachable")["type"] == "ENVIRONMENT_CHANGE"
    assert classify_failure("", "", tool="x")["confidence"] <= 0.2
    v = classify_failure("", "")
    assert v["type"] == FailureType.UNKNOWN.value  # never invented


# ---------- diagnosis ----------

def test_diagnosis_grades():
    rec = build_record("t", "g", {"tool": "calc", "action": "mul"},
                       "invalid argument: b", timed_out=False)
    d = diagnose(rec)
    assert d.grade in ("CONFIRMED", "LIKELY") and d.actionable is True
    assert "policy" in d.must_not_change and "weights" in d.must_not_change
    unk = build_record("t", "g", {"tool": "x"}, "")
    d2 = diagnose(unk)
    assert d2.grade == "UNCERTAIN" and d2.actionable is False


# ---------- strategy revision ----------

def test_revision_never_identical():
    rec = build_record("t", "g", {"tool": "calc", "action": "m",
                                  "input": {"a": 1}}, "invalid argument: b")
    d = diagnose(rec)
    rev = revision_for(d, {"tool": "calc", "action": "m", "input": {"a": 1}},
                       [{"tool": "calc", "action": "m", "input": {"a": 1, "b": 2}}])
    assert rev["action"]["input"] == {"a": 1, "b": 2}
    assert rev["from_diagnosis"] in ("CONFIRMED", "LIKELY")


# ---------- retry bounds + policy ----------

class _Policy:
    def __init__(self, allow=True, risk="LOW"):
        self.allow, self.risk = allow, risk

    def evaluate(self, capability, context=None, actor="system"):
        return {"allowed": self.allow, "reason": "t",
                "risk": self.risk, "capability": capability}


def test_retry_bounded_and_no_identical_repeat():
    budget = RetryBudget(max_retries=1, max_seconds=60)
    a = {"tool": "t", "action": "x", "input": {}}
    assert decide_retry(a, dict(a), budget, policy=_Policy())["allow"] is False
    assert decide_retry(a, {**a, "input": {"v": 1}}, budget,
                        policy=_Policy())["allow"] is True
    assert decide_retry(a, {**a, "input": {"v": 2}}, budget,
                        policy=_Policy())["allow"] is False  # exhausted


def test_retry_escalation_needs_approval():
    budget = RetryBudget(max_retries=3, max_seconds=60)
    failed = {"tool": "t", "action": "x", "input": {}, "risk": "LOW"}
    risky = {"tool": "t", "action": "y", "input": {}, "risk": "HIGH"}
    denied = decide_retry(failed, risky, budget, policy=_Policy(risk="HIGH"))
    assert denied["allow"] is False and "approval" in denied["reason"]
    ok = decide_retry(failed, risky, budget, policy=_Policy(risk="HIGH"),
                      approver=lambda v: True)
    assert ok["allow"] is True
    blocked = decide_retry(failed, {"tool": "z", "action": "w", "input": {}},
                           RetryBudget(), policy=_Policy(allow=False))
    assert blocked["allow"] is False  # failure never authorizes


# ---------- working memory + task state ----------

def test_world_state_provenance_and_provisional():
    ledger = TaskStateLedger("t1")
    fact = ledger.update("tool:calc", "rejected: INVALID_ARGUMENT",
                         observation="bad arg", source="obs", confidence=0.4)
    assert fact.provisional is True  # uncertain: never permanent truth
    firm = ledger.update("tool:calc", "accepts {a,b}", observation="ok",
                         source="verify", confidence=0.95)
    assert firm.provisional is False
    assert ledger.get("tool:calc") == "accepts {a,b}"
    assert ledger.firm()["tool:calc"] == "accepts {a,b}"


def test_contradiction_flagged():
    ledger = TaskStateLedger("t1")
    ledger.update("k", "v1", source="a", confidence=0.8)
    ledger.update("k", "v2", source="b", confidence=0.8)
    assert len(ledger.contradictions) == 1


# ---------- consolidation lifecycle ----------

class _Exp:
    def __init__(self):
        self.n = 0

    def record_rich(self, goal, **kw):
        self.n += 1

        class _R:
            experience_id = f"exp-{self.n}"
        return _R()


def test_lesson_lifecycle_candidate_to_consolidated():
    store = LessonStore()
    les = store.propose("Do X after Y.", scope="TASK")
    assert les.state == "CANDIDATE"
    assert store.consolidate(les.lesson_id)["ok"] is False  # too early
    store.record_validation(les.lesson_id, True)
    store.record_validation(les.lesson_id, True)
    assert store.get(les.lesson_id).state == "VALIDATED"
    exp = _Exp()
    out = store.consolidate(les.lesson_id, exp, task_id="t")
    assert out["ok"] is True and exp.n == 1


def test_failed_hypothesis_never_promoted():
    store = LessonStore()
    les = store.propose("Wrong idea.", scope="TASK")
    store.record_validation(les.lesson_id, False)
    store.record_validation(les.lesson_id, False)
    assert store.get(les.lesson_id).state == "CANDIDATE"
    assert store.consolidate(les.lesson_id)["ok"] is False


def test_stale_invalidation_and_expiry():
    import time

    store = LessonStore()
    les = store.propose("Temp rule.", ttl_s=0.05)
    time.sleep(0.08)
    assert store.get(les.lesson_id) is None  # expired
    les2 = store.propose("Old rule.")
    assert store.invalidate(les2.lesson_id, "env changed") is True
    assert store.get(les2.lesson_id).state == "CANDIDATE"


def test_contradiction_detection():
    store = LessonStore()
    a = store.propose("Always retry.", scope="TASK", task_family="f")
    store.record_validation(a.lesson_id, True)
    store.record_validation(a.lesson_id, True)
    store.propose("NOT: Always retry.", scope="TASK", task_family="f")
    assert len(store.contradictions) == 1


# ---------- scope + isolation ----------

def test_scope_enforcement_and_user_isolation():
    store = LessonStore()
    les = store.propose("User secret shortcut.", scope="TASK", owner="alice")
    # Unvalidated lessons are invisible everywhere (consumption contract).
    assert store.for_scope("TASK", owner="alice") == []
    store.record_validation(les.lesson_id, True)
    store.record_validation(les.lesson_id, True)
    assert store.for_scope("TASK", owner="alice") != []
    assert store.for_scope("TASK", owner="bob") == []  # no cross-user leak
    assert store.for_scope("GLOBAL") == []  # TASK never auto-global


def test_cross_task_isolation_in_executor():
    seen = {}

    def act(action):
        name = action.get("input", {}).get("name", "?")
        seen[name] = seen.get(name, 0) + 1
        return {"observation": "ok", "ok": True}

    def verify(action, result):
        return {"verified": result.get("ok", False)}

    ex = AdaptiveExecutor(owner="u1", max_retries=0)
    ex.run("task-A", "goal A", act, verify)
    ex.run("task-B", "goal B", act, verify)
    assert ex.lessons.for_scope("TASK", owner="u2") == []


# ---------- skill promotion gate ----------

class _Skills:
    def __init__(self):
        self.items = []

    def register(self, skill, validate=False, validation_note=""):
        skill["status"] = "VALIDATED" if validate else "PROPOSED"
        self.items.append(skill)
        return skill


def test_skill_promotion_requires_consolidated():
    store = LessonStore()
    skills = _Skills()
    les = store.propose("Use schema X for tool Y.")
    out = store.propose_skill(les.lesson_id, skills,
                              lambda l: {"skill_id": "s1",
                                         "procedure": [l.statement]})
    assert out["ok"] is False  # not consolidated yet
    for _ in range(2):
        store.record_validation(les.lesson_id, True)
    store.consolidate(les.lesson_id)
    out = store.propose_skill(les.lesson_id, skills,
                              lambda l: {"skill_id": "s1",
                                         "procedure": [l.statement]})
    assert out["ok"] is True and skills.items[0]["status"] == "PROPOSED"


# ---------- reflection ----------

def test_structured_reflection_schema():
    out = structured_reflect(
        {"failure_type": "INVALID_ARGUMENT", "observation": "bad b"},
        {"why": "bad arg", "grade": "CONFIRMED", "confidence": 0.9},
        {"reason": "different arguments"}, validated=True)
    assert out["promote_to_experience"] is True
    assert out["confidence"] == 0.9 and out["validated"] is True
    out2 = structured_reflect({"failure_type": "UNKNOWN"},
                              {"why": "?", "grade": "UNCERTAIN",
                               "confidence": 0.1},
                              {"reason": ""}, validated=False)
    assert out2["promote_to_experience"] is False


# ---------- env learner ----------

def test_env_learner_hypothesis_cycle():
    learner = EnvironmentLearner(max_steps=5)
    hyp = learner.hypothesize("pressing B toggles light")
    assert learner.confirm(hyp, lambda: True) is True
    assert hyp.confirmed and learner.rules == ["pressing B toggles light"]
    hyp2 = learner.hypothesize("pressing C toggles light")
    assert learner.confirm(hyp2, lambda: False) is False
    assert learner.failed == ["pressing C toggles light"]


# ---------- metrics + A/B ----------

def _flaky_tool_factory():
    calls = {"n": 0}

    def act(action):
        calls["n"] += 1
        if action.get("input", {}).get("fixed"):
            return {"observation": "result ok", "ok": True}
        if action.get("use_schema_v2"):
            return {"observation": "result ok", "ok": True}
        return {"observation": "invalid argument: b", "ok": False}

    def verify(action, result):
        return {"verified": bool(result.get("ok"))}
    return act, verify


def test_metrics_recovery_and_repeat_rates():
    from cognition.adaptation.metrics import LearningMetrics

    m = LearningMetrics()
    m.record("f", {"attempts": [{}, {}], "retries": 1, "verified": True,
                   "recovered": True, "wall_s": 1.0})
    m.record("f", {"attempts": [{}], "retries": 0, "verified": True,
                   "wall_s": 0.5})
    rep = m.report()["f"]
    assert rep["mistake_recovery_rate"] == 1.0
    assert rep["first_attempt_success_rate"] == 0.5


def test_ab_adaptive_beats_baseline_with_lesson():
    act, verify = _flaky_tool_factory()
    from cognition.adaptation.executor import AdaptiveExecutor

    tasks = [{"id": f"t{i}", "goal": "compute",
              "alternatives": [{"tool": "calc", "action": "mul",
                                "input": {"a": 1, "b": 2},
                                "use_schema_v2": True}]} for i in range(3)]
    out = ab_compare(tasks, act, verify,
                     lambda: AdaptiveExecutor(max_retries=2),
                     family="calc")
    assert out["baseline"]["success_rate"] == 0.0
    assert out["adaptive"]["success_rate"] == 1.0
    assert out["verdict"] == "adaptive-better"
    assert out["delta_success"] == 1.0


# ---------- offline export ----------

def test_offline_export_validated_only(tmp_path):
    traces = [{"recovered": True, "verified": True,
               "goal": "g", "lesson": {"statement": "s"},
               "attempts": [{"action": "a", "observation": "bad"},
                            {"action": "b", "observation": "ok"}]},
              {"recovered": False, "verified": False, "goal": "g2",
               "lesson": None, "attempts": []}]
    man = export_validated(traces, str(tmp_path / "exp.json"))
    assert man["samples"] == 1  # failures never exported


# ---------- regression protection ----------

def test_lesson_scope_does_not_leak_to_unrelated(tmp_path):
    store = LessonStore()
    les = store.propose("Calc needs b.", scope="TASK", task_family="calc")
    store.record_validation(les.lesson_id, True)
    store.record_validation(les.lesson_id, True)
    assert store.for_scope("TASK", task_family="other") == []
    assert len(store.for_scope("TASK", task_family="calc")) == 1


# ---------- 11-step acceptance demo ----------

def test_acceptance_fail_diagnose_revise_retry_verify_retain_reuse():
    """Steps 1-11: attempt, fail, detect, diagnose, revise, retry,
    succeed, verify, store, later task benefits, unrelated unaffected."""
    act, verify = _flaky_tool_factory()
    from cognition.adaptation.executor import AdaptiveExecutor
    from cognition.adaptation.metrics import LearningMetrics

    metrics = LearningMetrics()
    ex = AdaptiveExecutor(max_retries=3, owner="demo",
                          experience=_Exp())
    task = {"step": "compute", "alternatives": [
        {"tool": "calc", "action": "mul", "input": {"a": 1, "b": 2},
         "use_schema_v2": True}]}
    t1 = ex.run("demo-1", "compute it", act, verify,
                plan=["compute it"],
                alternatives=task["alternatives"])
    # 1-8: failed first, diagnosed, revised, retried, succeeded, verified
    assert len(t1["attempts"]) >= 2
    assert t1["attempts"][0]["verified"] is False
    assert t1["verified"] is True and t1["recovered"] is True
    # 9: validated lesson stored
    assert t1["lesson"] is not None and t1["lesson"]["consolidated"] is True
    metrics.record("demo", t1)
    # 10: a later related task consults the retained lesson scope
    retained = ex.lessons.for_scope("TASK", owner="demo")
    assert any("calc" in (l.statement) or "INVALID_ARGUMENT" in l.statement
               for l in retained)
    t2 = ex.run("demo-2", "compute again", act, verify,
                plan=["compute again"], alternatives=task["alternatives"])
    assert t2["verified"] is True
    metrics.record("demo", t2)
    rep = metrics.report()["demo"]
    assert rep["mistake_recovery_rate"] == 1.0
    # 11: unrelated family sees no lessons
    assert ex.lessons.for_scope("TASK", task_family="unrelated-xyz") == []
    # export contains exactly the recovered traces
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        man = export_validated([t1, t2], os.path.join(tmp, "e.json"))
        assert man["samples"] == 2
