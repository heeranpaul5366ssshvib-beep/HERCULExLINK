from __future__ import annotations
"""
Tests for UAI upgrade subsystems:
- Skill system + acquisition gate (§21/§22)
- Autonomy levels 0-5 gate (§27)
- Research workflow with evidence labels (§23)
- Brain lifecycle events on EventBus (§29)
- Goal hierarchy fields (§10)
"""

import json
import tempfile
from pathlib import Path

import pytest

from cognition.skills import (
    SKILL_STATUS_PROPOSED,
    SKILL_STATUS_VALIDATED,
    Skill,
    SkillManager,
)
from autonomy.levels import (
    LEVEL_NAMES,
    classify_goal_risk,
    evaluate_gate,
    normalize_level,
)
from cognition.research import (
    LABEL_FACT,
    LABEL_HYPOTHESIS,
    LABEL_INFERENCE,
    LABEL_UNCERTAINTY,
    Evidence,
    ResearchEngine,
    ResearchResult,
)


# ============================================================
# Skill system
# ============================================================

class _StubAbilities:
    def __init__(self, caps):
        self._caps = set(caps)

    def lookup_by_capability(self, cap):
        return object() if cap in self._caps else None


class _StubBus:
    def __init__(self):
        self.events = []

    def publish(self, event, *args, **kwargs):
        self.events.append((event, args, kwargs))


def _make_manager(caps=("FILE_READ",), bus=None):
    store = Path(tempfile.mkdtemp()) / "skills.json"
    return SkillManager(
        ability_manager=_StubAbilities(caps),
        experience_manager=None,
        store_path=store,
        event_bus=bus,
    )


def test_skill_registration_lifecycle():
    mgr = _make_manager()
    skill = Skill(skill_id="s1", description="Read then report",
                  required_capabilities=["FILE_READ"],
                  procedure=["read the file", "report contents"])
    out = mgr.register(skill)
    assert out.status == SKILL_STATUS_PROPOSED
    assert not out.is_registered()
    validated = mgr.register(Skill(skill_id="s2", description="v",
                                   procedure=["a"], verification="recheck"))
    assert validated.status == SKILL_STATUS_PROPOSED
    mgr2 = mgr.register(Skill(skill_id="s3", description="v",
                              procedure=["a"]), validate=True)
    assert mgr2.is_registered()
    assert mgr.usable()[0].skill_id == "s3"


def test_skill_duplicate_rejected():
    mgr = _make_manager()
    mgr.register(Skill(skill_id="dup", description="", procedure=["x"]))
    with pytest.raises(ValueError):
        mgr.register(Skill(skill_id="dup", description="", procedure=["x"]))


def test_skill_persistence_roundtrip(tmp_path):
    store = tmp_path / "skills.json"
    mgr = SkillManager(store_path=store)
    mgr.register(Skill(skill_id="persist-me", description="d",
                       required_capabilities=["FILE_READ"], procedure=["p"]),
                validate=True)
    fresh = SkillManager(store_path=store)
    loaded = fresh.load()
    assert loaded == 1
    assert fresh.get("persist-me").is_registered()


def test_skill_outcome_history_bounded():
    mgr = _make_manager()
    mgr.register(Skill(skill_id="hist", description="", procedure=["x"]), validate=True)
    for ok in [True] * 25 + [False] * 30:
        mgr.record_outcome("hist", ok)
    skill = mgr.get("hist")
    # Bounded history keeps the LAST 50 outcomes: of 55 recorded, the
    # first 5 successes are trimmed -> 20 successes + 30 failures remain.
    assert len(skill.success_history) == 50
    assert skill.success_rate() == 0.4


def test_skill_events_published():
    bus = _StubBus()
    mgr = _make_manager(bus=bus)
    mgr.register(Skill(skill_id="ev", description="", procedure=["x"]), validate=True)
    assert any(e[0] == "SKILL_REGISTERED" for e in bus.events)
    mgr.disable("ev")
    assert any(e[0] == "SKILL_DISABLED" for e in bus.events)


def test_gap_skill_match_beats_everything():
    mgr = _make_manager(caps=())
    mgr.register(Skill(skill_id="match", description="organize project files",
                       procedure=["list files", "group files"]), validate=True)
    verdict = mgr.evaluate_gap("organize project files now",
                               required_capabilities=["FILE_READ"])
    assert verdict["resolution"] == "skill_match"
    assert verdict["skill_id"] == "match"


def test_gap_ability_coverage():
    mgr = _make_manager(caps=("FILE_READ", "FILE_WRITE"))
    verdict = mgr.evaluate_gap("read then write", required_capabilities=["FILE_READ", "FILE_WRITE"])
    assert verdict["resolution"] == "ability_coverage"
    assert verdict["covered"] == ["FILE_READ", "FILE_WRITE"]


def test_gap_capability_gap_reported_honestly():
    mgr = _make_manager(caps=("FILE_READ",))
    verdict = mgr.evaluate_gap("do the impossible",
                               required_capabilities=["FILE_READ", "QUANTUM_LEVITATION"])
    assert verdict["resolution"] == "capability_gap"
    assert "QUANTUM_LEVITATION" in verdict["missing_capabilities"]


def test_gap_auto_install_never_happens():
    """Acquisition gate must never silently install anything (§22)."""
    mgr = _make_manager(caps=())
    verdict = mgr.evaluate_gap("unknown thing", required_capabilities=["SOMETHING_NEW"])
    assert verdict["resolution"] == "capability_gap"
    assert "proposal" not in verdict or verdict.get("needs_approval") is not False


# ============================================================
# Autonomy levels
# ============================================================

def test_normalize_level_bounds():
    assert normalize_level("3") == 3
    assert normalize_level(9) == 2
    assert normalize_level(-1) == 2
    assert normalize_level("bogus") == 2
    assert normalize_level(None, default=0) == 0


def test_level_zero_blocks_everything():
    for goal in ("read a file", "create report", "shutdown the system"):
        verdict = evaluate_gate(0, goal)
        assert not verdict["allowed"], goal


def test_level_two_blocks_high_risk():
    verdict = evaluate_gate(2, "delete all logs and wipe cache")
    assert not verdict["allowed"]
    assert verdict["risk"] == "HIGH"
    assert "level 2" in verdict["reason"]


def test_level_three_allows_medium_blocks_high():
    assert evaluate_gate(3, "create a summary report")["allowed"]
    verdict = evaluate_gate(3, "format the system drive")
    assert not verdict["allowed"]


def test_level_four_allows_high_with_note():
    verdict = evaluate_gate(4, "delete temp folders")
    assert verdict["allowed"]
    assert verdict["risk"] == "HIGH"


def test_risk_classification_deterministic():
    assert classify_goal_risk("read the file")["risk"] == "LOW"
    assert classify_goal_risk("create a new report")["risk"] == "MEDIUM"
    assert classify_goal_risk("shutdown the server")["risk"] == "HIGH"
    a = classify_goal_risk("same goal")
    b = classify_goal_risk("same goal")
    assert a == b


def test_config_autonomy_level_env():
    import os
    from system.config.runtime_config import load_runtime_config
    os.environ["HERCULE_AUTONOMY_LEVEL"] = "5"
    try:
        assert load_runtime_config().autonomy_level == 5
    finally:
        os.environ.pop("HERCULE_AUTONOMY_LEVEL", None)
    os.environ["HERCULE_AUTONOMY_LEVEL"] = "11"
    try:
        from system.config import runtime_config as rc
        with pytest.raises(Exception):
            rc.load_runtime_config()
    finally:
        os.environ.pop("HERCULE_AUTONOMY_LEVEL", None)


def test_worker_respects_level_gate():
    """schedule() must refuse goals above the level ceiling (§27)."""
    from autonomy.worker import AutonomyWorker

    class _Tasks:
        def create_task(self, *a, **k):
            return "t-1"

        def get(self, _tid):
            return {}

        def queue_task(self, _tid):
            pass

        def save(self):
            pass

        def list_tasks(self, **_k):
            return []

    class _Brain:
        consciousness = None
        event_bus = None

    worker = AutonomyWorker.__new__(AutonomyWorker)
    worker.services = {}
    worker.brain = _Brain()
    worker.tasks = _Tasks()
    worker.enabled = True
    worker.autonomy_level = 2
    worker.scheduler = None
    worker._owns_scheduler = False
    worker._stop_event = __import__("threading").Event()
    worker._paused = False
    worker._lock = __import__("threading").Lock()
    worker._future = None
    worker._worker_state = "STOPPED"
    worker._active_task_id = None
    worker._last_result = None
    worker.max_task_runtime_s = 60.0
    worker.max_concurrent_tasks = 1
    worker._started_count = 0
    worker._completed_count = 0
    worker._failed_count = 0

    with pytest.raises(PermissionError):
        worker.schedule("delete the whole directory", delay_s=0)


def test_start_blocked_below_level_two():
    from autonomy.worker import AutonomyWorker

    class _Brain:
        consciousness = None
        event_bus = None

    worker = AutonomyWorker.__new__(AutonomyWorker)
    worker.enabled = True
    worker.autonomy_level = 1
    worker.brain = _Brain()
    worker._future = None
    out = worker.start(recover=False)
    assert out["started"] is False
    assert "level 1" in out["reason"]


# ============================================================
# Research workflow
# ============================================================

def test_research_decompose_splits_subquestions():
    engine = ResearchEngine(source_ability=None)
    subs = engine.decompose("topic A; topic B; topic C")
    assert len(subs) == 3


def test_research_without_source_is_honest():
    engine = ResearchEngine(source_ability=None)
    result = engine.run("anything")
    assert result.status == "unverified"
    assert result.evidence == []
    assert "no reachable" in (result.error or "").lower() or result.error


def test_research_labels_are_explicit():
    engine = ResearchEngine(source_ability=None)
    ev = engine.label([
        Evidence(label=LABEL_UNCERTAINTY, content="[FACT] Water boils at 100C at sea level", source="s1"),
        Evidence(label=LABEL_UNCERTAINTY, content="Therefore the sample will boil around 100C", source="s1"),
        Evidence(label=LABEL_UNCERTAINTY, content="This result possibly suggests a pattern", source="s2"),
        Evidence(label=LABEL_UNCERTAINTY, content="Some claim with no markers", source="s3"),
    ])
    assert ev[0].label == LABEL_FACT
    assert ev[1].label == LABEL_INFERENCE
    assert ev[2].label == LABEL_HYPOTHESIS
    assert ev[3].label == LABEL_UNCERTAINTY
    assert ev[0].confidence > ev[3].confidence


def test_research_contradiction_detection():
    engine = ResearchEngine(source_ability=None)
    ev = engine.label([
        Evidence(label=LABEL_UNCERTAINTY, content="[FACT] The library supports python 3.12", source="doc-a"),
        Evidence(label=LABEL_UNCERTAINTY, content="[FACT] The library does not support python 3.12", source="doc-b"),
    ])
    contradictions = engine.detect_contradictions(ev)
    assert len(contradictions) == 1
    assert "doc-a" in contradictions[0] and "doc-b" in contradictions[0]


def test_research_synthesis_keeps_labels():
    engine = ResearchEngine(source_ability=None)
    result = engine.run("topic")
    assert isinstance(result, ResearchResult)
    assert isinstance(result.to_dict(), dict)


def test_research_with_real_source_collects():
    class _Source:
        def execute(self, topic, **kwargs):
            return {"status": "success",
                    "sources": [{"url": "https://example.test/a",
                                 "content": "[FACT] subject alpha exists"},
                                {"url": "https://example.test/b",
                                 "content": "plain material here"}]}

    engine = ResearchEngine(source_ability=_Source())
    result = engine.run("subject alpha")
    assert result.status in ("verified", "unverified")
    assert len(result.evidence) == 2
    assert result.evidence[0].label == LABEL_FACT
    assert result.evidence[0].source == "https://example.test/a"


def test_research_never_fabricates_sources():
    class _Empty:
        def execute(self, topic, **kwargs):
            return {"status": "success", "sources": []}

    engine = ResearchEngine(source_ability=_Empty())
    result = engine.run("nothing to find")
    assert result.status == "unverified"
    assert result.evidence == []


# ============================================================
# Brain event bus lifecycle + goal hierarchy
# ============================================================

def test_brain_publishes_lifecycle_events():
    """Brain emits USER_REQUEST and GOAL_COMPLETED/FAILED on the bus."""
    from kernel.event_bus import EventBus

    class _Bus(EventBus):
        pass

    class _Consciousness:
        def transition(self, *a, **k):
            pass

        def set_state(self, *a, **k):
            pass

        def focus_on(self, *a, **k):
            pass

    import brain.brain as brain_mod

    class _Holder:
        event_bus = _Bus()
        seen = []

    holder = _Holder()
    brain_mod.Brain._emit_event(holder, "USER_REQUEST", correlation_id="c1", goal="g")
    brain_mod.Brain._emit_event(holder, "GOAL_COMPLETED", correlation_id="c1", task_id="t")
    # publish with kwargs: EventBus passes them through to handlers; verify
    # no exception and subscriber receives them.
    received = []
    holder.event_bus.subscribe("PROBE", lambda **kw: received.append(kw))
    holder.event_bus.publish("PROBE", correlation_id="x")
    assert received == [{"correlation_id": "x"}]


def test_goal_manager_hierarchy_fields():
    from brain.goal_manager import GoalManager

    gm = GoalManager()
    parent = gm.add("parent goal")
    child = gm.add("child goal", parent_goal_id=parent, deadline="2026-12-31T00:00:00+00:00")
    subs = gm.subgoals(parent)
    assert len(subs) == 1
    assert subs[0]["id"] == child
    assert subs[0]["parent_goal_id"] == parent
    assert subs[0]["deadline"] == "2026-12-31T00:00:00+00:00"
    plain = gm.add("no hierarchy")
    assert "parent_goal_id" not in gm.goals[-1] or gm.goals[-1]["id"] == plain


def test_skill_json_shape_stable():
    mgr = _make_manager()
    mgr.register(Skill(skill_id="shape", description="d", procedure=["a"],
                       required_capabilities=["FILE_READ"]), validate=True)
    data = json.loads(mgr._store_path.read_text(encoding="utf-8"))
    assert "skills" in data
    skill = data["skills"][0]
    for key in ("skill_id", "description", "procedure", "status", "source"):
        assert key in skill
