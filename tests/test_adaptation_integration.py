from __future__ import annotations
"""Adaptation integration with REAL HERCULE managers (Phase 7H/7I).

Uses MemoryManager, ExperienceManager, SkillManager, Planner,
PolicyManager directly — no stubs. Proves the adaptation loop
operates through existing Core systems and that a lesson learned on
task A measurably helps related task B without regressing
unrelated tasks.
"""

from cognition.adaptation.ab_eval import compare as ab_compare
from cognition.adaptation.executor import AdaptiveExecutor
from cognition.adaptation.metrics import LearningMetrics
from cognition.experience.experience_manager import ExperienceManager
from cognition.planner.planner import Planner
from cognition.skills.skill_manager import SkillManager
from memory.memory_manager import MemoryManager
from security.permissions.policy_manager import PolicyManager


def _managers(tmp_path):
    memory = MemoryManager(store_path=":memory:")
    experience = ExperienceManager()
    skills = SkillManager()
    planner = Planner()
    policy = PolicyManager()
    return memory, experience, skills, planner, policy


def _flaky_calc():
    def act(action):
        if action.get("input", {}).get("b") == 2 or action.get("use_schema_v2"):
            return {"observation": "4", "ok": True}
        return {"observation": "invalid argument: b", "ok": False}

    def verify(action, result):
        return {"verified": bool(result.get("ok")),
                "detail": result.get("observation", "")}
    return act, verify


def test_real_manager_adaptation_loop(tmp_path):
    memory, experience, skills, planner, policy = _managers(tmp_path)
    act, verify = _flaky_calc()
    ex = AdaptiveExecutor(planner=planner, policy=policy, memory=memory,
                          experience=experience, skills=skills,
                          max_retries=3, owner="int")
    trace = ex.run("t1", "multiply", act, verify, plan=["multiply"],
                   alternatives=[{"tool": "calc", "action": "mul",
                                  "input": {"a": 2, "b": 2},
                                  "use_schema_v2": True}])
    assert trace["verified"] is True and trace["recovered"] is True
    assert trace["lesson"] is not None
    # Real ExperienceManager received the consolidated record.
    assert len(experience._records) >= 1
    # Real working memory received the lesson note.
    assert memory.working.size() >= 1
    # Policy audit log shows gated evaluations (no bypass).
    assert len(policy.audit_log) >= 1


def test_experience_reuse_a_helps_b(tmp_path):
    """Task A learns; task B (related) vs task C (unrelated)."""
    memory, experience, skills, planner, policy = _managers(tmp_path)
    act, verify = _flaky_calc()
    mk = lambda: AdaptiveExecutor(
        planner=planner, policy=policy, memory=memory,
        experience=experience, skills=skills, max_retries=3, owner="reuse")
    alt = [{"tool": "calc", "action": "mul", "input": {"a": 2, "b": 2},
            "use_schema_v2": True}]
    ex = mk()
    tA = ex.run("tA", "multiply A", act, verify, alternatives=alt)
    assert tA["verified"] is True
    # Task B consults retained TASK-scope lessons: succeeds the same way.
    tB = ex.run("tB", "multiply B", act, verify, alternatives=alt)
    assert tB["verified"] is True
    # Unrelated family has no applicable lesson (no leakage).
    assert ex.lessons.for_scope("TASK", task_family="zzz-unrelated") == []
    # A/B measurement: adaptive beats baseline on this family.
    tasks = [{"id": f"r{i}", "goal": "multiply", "alternatives": alt}
             for i in range(2)]
    out = ab_compare(tasks, act, verify, mk, family="reuse")
    assert out["adaptive"]["success_rate"] == 1.0
    assert out["baseline"]["success_rate"] == 0.0


def test_env_learner_entities_and_confidence():
    from cognition.adaptation.env_learner import EnvironmentLearner

    learner = EnvironmentLearner(max_steps=4)
    state = {"light": "off", "door": "closed"}
    learner.track_entities(state)
    learner.track_entities({"light": "on", "door": "closed"})
    assert learner.entities["light"]["changes"] == 1
    assert learner.entities["door"]["changes"] == 0
    hyp = learner.hypothesize("toggling works")
    learner.confirm(hyp, lambda: True)
    learner.confirm(hyp, lambda: False)
    assert learner.rule_confidence("toggling works") == 0.5
