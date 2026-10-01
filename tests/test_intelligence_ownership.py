from brain.brain import Brain
from cognition.contracts import Goal, Decision, ReasoningResult, Plan
from cognition.ownership import responsibility_matrix, get_authoritative_owner
from cognition.task_manager.task_manager import TaskManager
from memory.memory_manager import MemoryManager
from models.model_manager import ModelManager
from models.router.model_router import ModelRouter
from security.permissions.policy_manager import PolicyManager
from abilities.ability_manager import AbilityManager


class DummyOrchestrator:
    def __init__(self):
        self.pipeline = type("Pipeline", (), {"add_stage": lambda self, *a, **k: None, "execute": lambda self, prompt: {"prompt": prompt, "ok": True}})()
        self.models = type("Models", (), {"generate": lambda self, *a, **k: {"result": "ok"}})()
        self.executor = type("Executor", (), {"execute": lambda self, task, *a, **k: {"task": task, "ok": True}})()
        self.memory = type("Memory", (), {"remember_event": lambda self, *a, **k: True})()
        self.agent = type("Agent", (), {"think": lambda self, prompt: f"response:{prompt}"})()


def test_responsibility_matrix_has_unique_authorities():
    matrix = responsibility_matrix()
    planning = get_authoritative_owner("planning")
    reasoning = get_authoritative_owner("reasoning")
    decision = get_authoritative_owner("decision making")
    assert planning == "cognition.planner.planner.Planner"
    assert reasoning == "cognition.reasoning.reasoner.Reasoner"
    assert decision == "cognition.decision.decision_engine.DecisionEngine"
    assert matrix
    assert any(row["Responsibility"] == "planning" for row in matrix)


def test_brain_routes_to_canonical_planner_and_reasoning():
    brain = Brain(DummyOrchestrator())
    assert brain.authoritative_planner is not None
    assert brain.authoritative_decision is not None
    plan = brain.create_plan("Fix router")
    assert plan
    assert plan[0]["goal"] == "Fix router"
    assert brain.reason("Diagnose failure")


def test_contract_objects_are_structured_and_traceable():
    goal = Goal(name="router-stability", description="Restore router stability", priority=10)
    reasoning = ReasoningResult(goal_id=goal.id, facts=["Model mismatch exists"], observations=["Fallback adapter is healthy"], assumptions=["The issue is in router selection"], hypotheses=["wrong adapter is chosen"], unresolved_questions=["Which adapter matches the task?"], confidence=0.91)
    decision = Decision(options=["use mock", "use ollama"], selected_option="use ollama", rationale={"confidence": 0.9}, risk="low")
    plan = Plan(goal_id=goal.id, steps=["Check availability", "Route to healthy adapter"], dependencies=[], required_capabilities=["routing"], verification_criteria=["task completes"])

    assert goal.id
    assert reasoning.correlation_id
    assert decision.selected_option == "use ollama"
    assert plan.goal_id == goal.id


def test_canonical_intelligence_path_uses_authoritative_components():
    brain = Brain(DummyOrchestrator())
    assert brain.authoritative_planner.__class__.__module__ == "cognition.planner.planner"
    assert brain.authoritative_reasoner.__class__.__module__ == "cognition.reasoning.reasoner"
    assert brain.authoritative_decision.__class__.__module__ == "cognition.decision.decision_engine"
    assert "REASONING" in brain.canonical_execution_path
    assert "PLANNER" not in str(brain.canonical_execution_path)


def test_orchestrator_and_task_manager_remain_authoritative_for_execution_lifecycle():
    task_manager = TaskManager()
    task_id = task_manager.create_task("Route to a healthy adapter")
    assert task_manager.get(task_id)["status"] == "CREATED"
    task_manager.start(task_id)
    assert task_manager.get(task_id)["status"] == "RUNNING"


def test_model_router_memory_and_security_are_authoritative_boundaries():
    model_manager = ModelManager(default_model="llama3")
    assert isinstance(model_manager.router, ModelRouter)
    memory = MemoryManager()
    memory.remember({"text": "model routing should remain central"})
    assert memory.history()
    policy = PolicyManager()
    policy.set_permission("FILE_WRITE", False)
    decision = policy.evaluate("FILE_WRITE", {"risk": "HIGH"}, actor="unit-test")
    assert decision["allowed"] is False


def test_tool_execution_naturally_respects_policy_and_verification():
    class DummyAbility:
        name = "file_write"
        permission = "FILE_WRITE"
        enabled = True
        risk = "HIGH"

        def execute(self, *args, **kwargs):
            return {"status": "ok"}

    manager = AbilityManager(policy=PolicyManager())
    manager.registry.register(DummyAbility())
    manager.policy.set_permission("FILE_WRITE", False)
    try:
        manager.execute("file_write", "should-not-run")
        assert False
    except RuntimeError:
        pass

    task_manager = TaskManager()
    task_id = task_manager.create_task("verify route", expected_result="done")
    task_manager.start(task_id)
    task_manager.complete(task_id, {"result": "done"}, validation={"verified": True})
    assert task_manager.get(task_id)["status"] == "COMPLETED"
