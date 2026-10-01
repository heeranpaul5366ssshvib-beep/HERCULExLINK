from __future__ import annotations
"""Phase I: goal-hierarchy validation (UAI §10).

``parent_goal_id`` / ``deadline`` are additive GoalManager fields.
Covers creation, retrieval, completion, failure, dependency
ordering, deadline representation, nesting, legacy compatibility,
and one live Brain integration proving hierarchy survives planning.
"""

import pytest

from brain.goal_manager import GoalManager


@pytest.fixture()
def gm():
    return GoalManager()


def test_parent_child_creation_and_retrieval(gm):
    parent = gm.add("ship release")
    child = gm.add("write notes", parent_goal_id=parent,
                   deadline="2026-12-31T00:00:00+00:00")
    subs = gm.subgoals(parent)
    assert len(subs) == 1
    assert subs[0]["id"] == child
    assert subs[0]["parent_goal_id"] == parent
    assert subs[0]["deadline"] == "2026-12-31T00:00:00+00:00"
    assert gm.get(child)["goal"] == "write notes"


def test_plain_goals_carry_no_hierarchy_keys(gm):
    gm.add("standalone")
    record = gm.goals[-1]
    assert "parent_goal_id" not in record
    assert "deadline" not in record
    assert gm.subgoals(record["id"]) == []


def test_three_level_nesting(gm):
    top = gm.add("top")
    mid = gm.add("mid", parent_goal_id=top)
    leaf = gm.add("leaf", parent_goal_id=mid)
    assert [g["id"] for g in gm.subgoals(top)] == [mid]
    assert [g["id"] for g in gm.subgoals(mid)] == [leaf]
    assert gm.subgoals(leaf) == []


def test_child_completion_is_independent_of_parent(gm):
    parent = gm.add("parent")
    child = gm.add("child", parent_goal_id=parent)
    assert gm.activate(child) is True
    assert gm.complete(child) is True
    assert gm.get(child)["status"] == "COMPLETED"
    assert gm.get(parent)["status"] == "QUEUED"  # parent unaffected
    assert gm.complete(parent) is True


def test_child_failure_does_not_fail_parent(gm):
    parent = gm.add("parent")
    child = gm.add("child", parent_goal_id=parent)
    assert gm.fail(child, "boom") is True
    assert gm.get(child)["status"] == "FAILED"
    assert gm.get(parent)["status"] == "QUEUED"


def test_dependency_ordering_with_hierarchy(gm):
    first = gm.add("first step")
    second = gm.add("second step", dependencies=[first],
                    parent_goal_id=gm.add("parent"))
    assert gm.dependencies_met(second) is False
    gm.activate(first)
    gm.complete(first)
    assert gm.dependencies_met(second) is True


def test_deadline_is_verbatim_iso_representation(gm):
    deadline = "2026-06-01T12:00:00+00:00"
    gid = gm.add("timed", deadline=deadline)
    assert gm.get(gid)["deadline"] == deadline


def test_priority_ordering_ignores_hierarchy_fields(gm):
    gm.add("low", priority=1)
    parent = gm.add("parent", priority=9)
    gm.add("child of parent", parent_goal_id=parent, priority=0)
    queued = gm.queued_goals()
    assert queued[0]["id"] == parent  # priority still rules


def test_legacy_helpers_unaffected(gm):
    gm.add_goal("legacy")
    assert gm.active_goals()
    gm.complete_goal(0)
    assert gm.completed_goals()
    gm.clear()
    assert gm.goals == []


def test_terminal_transitions_still_guarded(gm):
    gid = gm.add("g")
    assert gm.complete("missing") is False
    gm.activate(gid)
    gm.complete(gid)
    assert gm.fail(gid, "late") is False  # terminal states stick
    assert gm.cancel(gid) is False


def test_brain_hierarchy_survives_planning(monkeypatch):
    """Live Brain: parent + deadline persist around a real run_cycle."""
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    parent = brain.goals.add("parent release",
                             deadline="2026-12-31T00:00:00+00:00")
    report = brain.run_cycle("calculate 2+2")
    assert report["status"] == "completed"
    assert report["goal_id"]  # cycle goal tracked independently
    assert brain.goals.get(parent)["deadline"] == "2026-12-31T00:00:00+00:00"
    assert brain.goals.subgoals(parent) == []
    assert brain.health()["active_goals"] >= 1
